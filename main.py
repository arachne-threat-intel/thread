# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been renamed from `tram.py`
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import aiohttp_jinja2
import asyncio
import argparse
import jinja2
import logging
import os
import sys
import yaml

from aiohttp import web
from datetime import datetime
from threadcomponents.database.dao import Dao, DB_POSTGRESQL, DB_SQLITE
from threadcomponents.handlers.web_api import WebAPI
from threadcomponents.reports.report_exporter import ReportExporter
from threadcomponents.service.attack_data_svc import AttackDataService
from threadcomponents.service.data_svc import DataService
from threadcomponents.service.ml_svc import MLService
from threadcomponents.service.reg_svc import RegService
from threadcomponents.service.rest_svc import RestService
from threadcomponents.service.token_svc import TokenService
from threadcomponents.service.web_svc import WebService

# If calling Thread from outside the project directory, then we need to specify
# a directory prefix (e.g. when Thread is a subdirectory)
dir_prefix = ""
# The types of sources for building the database
ONLINE_BUILD_SOURCE = "taxii-server"
OFFLINE_BUILD_SOURCE = "local-json"
# Have we scheduled the attack-data-update function?
ATTACK_DATA_UPDATES_SCHEDULED = False


async def repeat(interval, func, *args, **kwargs):
    """Run a function (func) every interval seconds. Credit to https://stackoverflow.com/a/55505152"""
    if not callable(func):
        raise TypeError("Function is not callable.")
    while True:
        await asyncio.gather(func(*args, **kwargs), asyncio.sleep(interval))


async def update_attack_data_scheduler():
    """Function to schedule and execute the monthly updates of the attack data."""
    global ATTACK_DATA_UPDATES_SCHEDULED
    # If this method has just been scheduled, we don't want to run it because we've done updates recently
    if not ATTACK_DATA_UPDATES_SCHEDULED:
        ATTACK_DATA_UPDATES_SCHEDULED = True
        return
    # Check if we are at the beginning of the month, if so, it's the right day for updates
    today = datetime.now()
    if today.day != 1:
        return
    logging.info("UPDATE ATTACK DATA: START")
    # Pick a quiet/suitable time to do the update (early in the next morning)
    update_datetime = datetime(today.year, today.month, today.day + 1, 1, 0, 0)
    update_time_diff = update_datetime - today
    await asyncio.sleep(update_time_diff.seconds)
    await website_handler.fetch_and_update_attack_data()
    logging.info("UPDATE ATTACK DATA: END")


async def background_tasks(taxii_local=ONLINE_BUILD_SOURCE, build=False, json_file=None):
    """
    Function to run background tasks at startup
    :param taxii_local: Expects 'online' or 'offline' to specify the build type.
    :param build: Defines whether or not a new database will be rebuilt
    :param json_file: Expects a path to the enterprise attack json if the 'json' build method is called.
    :return: nil
    """
    if build:
        await data_svc.reload_database()
        if taxii_local == ONLINE_BUILD_SOURCE:
            try:
                await rest_svc.fetch_and_update_attack_data()
            except Exception as exc:
                logging.critical(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                    "COULD NOT CONNECT TO TAXII SERVERS: {}\nPLEASE UPDATE CONFIG `taxii-local` "
                    "FOR OFFLINE DATABASE BUILDING\n"
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!".format(exc)
                )
                sys.exit()
        elif taxii_local == OFFLINE_BUILD_SOURCE and json_file:
            await data_svc.insert_attack_json_data(json_file)
        await data_svc.set_regions_data()
        await data_svc.set_countries_data()
        await data_svc.insert_category_json_data()
        await data_svc.insert_keyword_json_data()


async def init(host, port, app_setup_func=None):
    """
    Function to initialize the aiohttp app

    :param host: Address to reach webserver on
    :param port: Port to listen on
    :param app_setup_func: Optional, a function that applies extra config to the app
    :return: nil
    """
    # Run any required functions before the app is launched
    await website_handler.pre_launch_init()

    logging.info("server starting: %s:%s" % (host, port))
    webapp_dir = os.path.join(dir_prefix, "webapp")
    logging.info("webapp dir is %s" % webapp_dir)

    app = web.Application(middlewares=[WebAPI.req_handler])
    app.router.add_route("GET", web_svc.get_route(WebService.HOME_KEY), website_handler.index)
    app.router.add_route("GET", web_svc.get_route(WebService.EDIT_KEY), website_handler.edit)
    app.router.add_route("GET", web_svc.get_route(WebService.ABOUT_KEY), website_handler.about)
    app.router.add_route("GET", web_svc.get_route(WebService.HOW_IT_WORKS_KEY), website_handler.how_it_works)
    app.router.add_route("*", web_svc.get_route(WebService.REST_KEY), website_handler.rest_api)
    app.router.add_route("GET", web_svc.get_route(WebService.EXPORT_PDF_KEY), website_handler.pdf_export)
    app.router.add_route("GET", web_svc.get_route(WebService.EXPORT_NAV_KEY), website_handler.nav_export)
    app.router.add_route("GET", web_svc.get_route(WebService.EXPORT_AFB_KEY), website_handler.afb_export)
    app.router.add_route("GET", web_svc.get_route(WebService.COOKIE_KEY), website_handler.accept_cookies)
    if not web_svc.is_local:
        app.router.add_route("GET", web_svc.get_route(WebService.WHAT_TO_SUBMIT_KEY), website_handler.what_to_submit)
    app.router.add_static(web_svc.get_route(WebService.STATIC_KEY), os.path.join(webapp_dir, "theme"))

    # If extra app-setup is required, do this
    if callable(app_setup_func):
        app_setup_func(app)

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(webapp_dir, "html")))
    web_svc.set_internal_app(app)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    # First action after app-initialisation is to resume any reports left in the queue from a previous session
    await rest_svc.check_queue()


def start(host, port, taxii_local=ONLINE_BUILD_SOURCE, build=False, json_file=None, app_setup_func=None):
    """
    Main function to start app
    :param host: Address to reach webserver on
    :param port: Port to listen on
    :param taxii_local: Expects online or offline build_source to specify the build type
    :param build: Defines whether or not a new database will be rebuilt
    :param json_file: Expects a path to the enterprise attack json if the 'offline' build method is called
    :param app_setup_func: Optional, a function that applies extra config to the app
    :return: nil
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init(host, port, app_setup_func=app_setup_func))
    loop.create_task(background_tasks(taxii_local=taxii_local, build=build, json_file=json_file))

    if taxii_local == ONLINE_BUILD_SOURCE:
        # Schedule the function to update the attack-data (check daily if it is time to do so)
        asyncio.ensure_future(repeat(86400, update_attack_data_scheduler))

    if not web_svc.is_local:
        # Schedule the function to tidy up reports and fetch updated keywords
        asyncio.ensure_future(repeat(86400, data_svc.remove_expired_reports))
        asyncio.ensure_future(repeat(86400, website_handler.fetch_and_update_keywords))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def retrain_deps(directory_prefix=""):
    # Read from config
    with open(os.path.join(directory_prefix, "threadcomponents", "conf", "config.yml")) as c:
        config = yaml.safe_load(c)
        json_file = config.get("json_file", None)
        update_json_file = config.get("update_json_file", False)
        json_file_indent = config.get("json_file_indent", 2)
        json_file_path = os.path.join(directory_prefix, "threadcomponents", "models", json_file) if json_file else None

    # Check int parameters are ints
    int_error = "%s config set incorrectly: expected a number"
    try:
        int(json_file_indent)
    except ValueError:
        raise ValueError(int_error % "json_file_indent")

    # Initialise DAO, start services and initiate main function
    token_svc = TokenService()
    ml_svc = MLService(token_svc=token_svc, dir_prefix=directory_prefix)
    attack_file_settings = dict(filepath=json_file_path, update=update_json_file, indent=json_file_indent)
    attack_data_svc = AttackDataService(dir_prefix=directory_prefix, attack_file_settings=attack_file_settings)

    return ml_svc, attack_data_svc


def main(directory_prefix="", route_prefix=None, app_setup_func=None, db_connection_func=None):
    global data_svc, dir_prefix, ml_svc, rest_svc, web_svc, website_handler

    dir_prefix = directory_prefix
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.info("Welcome to Thread")

    # Read from config
    with open(os.path.join(dir_prefix, "threadcomponents", "conf", "config.yml")) as c:
        config = yaml.safe_load(c)
        is_local = config.get("run-local", True)
        db_conf = config.get("db-engine", DB_SQLITE)
        conf_build = config.get("build", True)
        host = config.get("host", "0.0.0.0")
        port = config.get("port", 9999)
        taxii_local = config.get("taxii-local", ONLINE_BUILD_SOURCE)
        js_src = config.get("js-libraries", "js-online-src")
        max_tasks = config.get("max-analysis-tasks", 1)
        queue_limit = config.get("queue_limit", 0)
        sentence_limit = config.get("sentence_limit", 0)
        json_file = config.get("json_file", None)
        update_json_file = config.get("update_json_file", False)
        json_file_indent = config.get("json_file_indent", 2)
        json_file_path = os.path.join(dir_prefix, "threadcomponents", "models", json_file) if json_file else None
        attack_dict = None

    # Set the attack dictionary filepath if applicable
    if conf_build and taxii_local == OFFLINE_BUILD_SOURCE and json_file_path and os.path.isfile(json_file_path):
        logging.info("Will build model from static file")
        attack_dict = os.path.abspath(json_file_path)

    # Check int parameters are ints
    int_error = "%s config set incorrectly: expected a number"
    try:
        if queue_limit < 1:
            queue_limit = None
    except TypeError:
        raise ValueError(int_error % "queue_limit")
    try:
        if sentence_limit < 1:
            sentence_limit = None
    except TypeError:
        raise ValueError(int_error % "sentence_limit")
    try:
        max_tasks = max(1, max_tasks)
    except TypeError:
        raise ValueError(int_error % "max-analysis-tasks")
    try:
        int(port)
    except ValueError:
        raise ValueError(int_error % "port")
    try:
        int(json_file_indent)
    except ValueError:
        raise ValueError(int_error % "json_file_indent")

    # Determine DB engine to use
    db_obj = None
    if db_conf == DB_SQLITE:
        from threadcomponents.database.thread_sqlite3 import ThreadSQLite

        db_obj = ThreadSQLite(os.path.join(dir_prefix, "threadcomponents", "database", "thread.db"))
    elif db_conf == DB_POSTGRESQL:
        # Import here to avoid PostgreSQL requirements needed for non-PostgreSQL use
        from threadcomponents.database.thread_postgresql import ThreadPostgreSQL

        db_obj = ThreadPostgreSQL(db_connection_func=db_connection_func)

    # Initialise DAO, start services and initiate main function
    dao = Dao(engine=db_obj)
    web_svc = WebService(route_prefix=route_prefix, is_local=is_local)
    reg_svc = RegService()
    data_svc = DataService(dao=dao, web_svc=web_svc, dir_prefix=dir_prefix)
    token_svc = TokenService()
    ml_svc = MLService(token_svc=token_svc, dir_prefix=dir_prefix)
    attack_file_settings = dict(filepath=json_file_path, update=update_json_file, indent=json_file_indent)
    attack_data_svc = AttackDataService(dir_prefix=dir_prefix, attack_file_settings=attack_file_settings)
    rest_svc = RestService(
        web_svc=web_svc,
        reg_svc=reg_svc,
        data_svc=data_svc,
        token_svc=token_svc,
        ml_svc=ml_svc,
        dao=dao,
        queue_limit=queue_limit,
        sentence_limit=sentence_limit,
        max_tasks=max_tasks,
        attack_data_svc=attack_data_svc,
    )
    services = dict(
        dao=dao,
        data_svc=data_svc,
        ml_svc=ml_svc,
        reg_svc=reg_svc,
        web_svc=web_svc,
        rest_svc=rest_svc,
        token_svc=token_svc,
        attack_data_svc=attack_data_svc,
    )
    report_exporter = ReportExporter(services=services)
    website_handler = WebAPI(services=services, report_exporter=report_exporter, js_src=js_src)
    start(host, port, taxii_local=taxii_local, build=conf_build, json_file=attack_dict, app_setup_func=app_setup_func)


if __name__ == "__main__":
    # Help information for the program
    parser = argparse.ArgumentParser(description="Launch the Thread webapp.")
    parser.add_argument("--build-db", action="store_true", help="builds the (PostgreSQL) database")
    parser.add_argument("--schema", help="the schema file to use if --build-db option is used")
    given_args = vars(parser.parse_args())

    if given_args.get("build_db"):
        schema = given_args.get("schema")
        # Import here to avoid PostgreSQL requirements needed for non-PostgreSQL use
        from threadcomponents.database.thread_postgresql import build_db as build_postgresql

        build_postgresql(schema)
    else:
        main()

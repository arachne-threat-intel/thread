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
from datetime import date
from threadcomponents.database.dao import Dao, DB_POSTGRESQL, DB_SQLITE
from threadcomponents.handlers.web_api import WebAPI
from threadcomponents.service.data_svc import DataService
from threadcomponents.service.ml_svc import MLService
from threadcomponents.service.reg_svc import RegService
from threadcomponents.service.rest_svc import RestService
from threadcomponents.service.web_svc import WebService

# If calling Thread from outside the project directory, then we need to specify
# a directory prefix (e.g. when Thread is a subdirectory)
dir_prefix = ''
# The types of sources for building the database
ONLINE_BUILD_SOURCE = 'taxii-server'
OFFLINE_BUILD_SOURCE = 'local-json'
# Have we scheduled the attack-data-update function?
ATTACK_DATA_UPDATES_SCHEDULED = True


async def repeat(interval, func, *args, **kwargs):
    """Run a function (func) every interval seconds. Credit to https://stackoverflow.com/a/55505152"""
    if not callable(func):
        raise TypeError('Function is not callable.')
    while True:
        await asyncio.gather(func(*args, **kwargs), asyncio.sleep(interval))


async def update_attack_data_scheduler():
    """Function to schedule and execute the monthly updates of the attack data."""
    global ATTACK_DATA_UPDATES_SCHEDULED
    # If this method has just been scheduled, we don't want to run it because we've done updates recently
    if ATTACK_DATA_UPDATES_SCHEDULED:
        ATTACK_DATA_UPDATES_SCHEDULED = False
        return
    # Check if we are at the beginning of the month, if so, it's time for updates
    day_today = date.today().day
    if day_today != 1:
        return
    await website_handler.fetch_and_update_attack_data()


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
                await rest_svc.insert_attack_data()
            except Exception as exc:
                logging.critical('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
                                 'COULD NOT CONNECT TO TAXII SERVERS: {}\nPLEASE UPDATE CONFIG `taxii-local` '
                                 'FOR OFFLINE DATABASE BUILDING\n'
                                 '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'.format(exc))
                sys.exit()
            try:
                # Schedule the function to update the attack-data (check daily if it is time to do so)
                update_attack_task = asyncio.ensure_future(repeat(86400, update_attack_data_scheduler))
                await update_attack_task
            except Exception as exc:
                logging.error('Could not schedule repeated executions of attack-update function: {}'.format(exc))
        elif taxii_local == OFFLINE_BUILD_SOURCE and json_file:
            await data_svc.insert_attack_json_data(json_file)


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

    logging.info('server starting: %s:%s' % (host, port))
    webapp_dir = os.path.join(dir_prefix, 'webapp')
    logging.info('webapp dir is %s' % webapp_dir)

    app = web.Application(middlewares=[WebAPI.req_handler])
    app.router.add_route('GET', web_svc.get_route(WebService.HOME_KEY), website_handler.index)
    app.router.add_route('GET', web_svc.get_route(WebService.EDIT_KEY), website_handler.edit)
    app.router.add_route('GET', web_svc.get_route(WebService.ABOUT_KEY), website_handler.about)
    app.router.add_route('*', web_svc.get_route(WebService.REST_KEY), website_handler.rest_api)
    app.router.add_route('GET', web_svc.get_route(WebService.EXPORT_PDF_KEY), website_handler.pdf_export)
    app.router.add_route('GET', web_svc.get_route(WebService.EXPORT_NAV_KEY), website_handler.nav_export)
    app.router.add_route('GET', web_svc.get_route(WebService.COOKIE_KEY), website_handler.accept_cookies)
    app.router.add_static(web_svc.get_route(WebService.STATIC_KEY), os.path.join(webapp_dir, 'theme'))

    # If extra app-setup is required, do this
    if callable(app_setup_func):
        app_setup_func(app)

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(webapp_dir, 'html')))
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
    loop = asyncio.get_event_loop()
    loop.create_task(background_tasks(taxii_local=taxii_local, build=build, json_file=json_file))
    loop.run_until_complete(init(host, port, app_setup_func=app_setup_func))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


def main(directory_prefix='', route_prefix=None, app_setup_func=None):
    global data_svc, dir_prefix, ml_svc, rest_svc, web_svc, website_handler

    dir_prefix = directory_prefix
    logging.getLogger().setLevel(logging.INFO)
    logging.info('Welcome to Thread')

    # Read from config
    with open(os.path.join(dir_prefix, 'threadcomponents', 'conf', 'config.yml')) as c:
        config = yaml.safe_load(c)
        is_local = config.get('run-local', True)
        db_conf = config.get('db-engine', DB_SQLITE)
        conf_build = config.get('build', True)
        host = config.get('host', '0.0.0.0')
        port = config.get('port', 9999)
        taxii_local = config.get('taxii-local', ONLINE_BUILD_SOURCE)
        js_src = config.get('js-libraries', 'js-online-src')
        max_tasks = config.get('max-analysis-tasks', 1)
        queue_limit = config.get('queue_limit', 0)
        json_file = config.get('json_file', None)
        json_file_path = os.path.join(dir_prefix, 'threadcomponents', 'models', json_file) if json_file else None
        attack_dict = None
    # Set the attack dictionary filepath if applicable
    if conf_build and taxii_local == OFFLINE_BUILD_SOURCE and json_file_path and os.path.isfile(json_file_path):
        logging.info('Will build model from static file')
        attack_dict = os.path.abspath(json_file_path)
    # Check int parameters are ints
    int_error = '%s config set incorrectly: expected a number'
    try:
        if queue_limit < 1:
            queue_limit = None
    except TypeError:
        raise ValueError(int_error % 'queue_limit')
    try:
        max_tasks = max(1, max_tasks)
    except TypeError:
        raise ValueError(int_error % 'max-analysis-tasks')
    try:
        int(port)
    except ValueError:
        raise ValueError(int_error % 'port')
    # Determine DB engine to use
    db_obj = None
    if db_conf == DB_SQLITE:
        from threadcomponents.database.thread_sqlite3 import ThreadSQLite
        db_obj = ThreadSQLite(os.path.join(dir_prefix, 'threadcomponents', 'database', 'thread.db'))
    elif db_conf == DB_POSTGRESQL:
        # Import here to avoid PostgreSQL requirements needed for non-PostgreSQL use
        from threadcomponents.database.thread_postgresql import ThreadPostgreSQL
        db_obj = ThreadPostgreSQL()

    # Initialise DAO, start services and initiate main function
    dao = Dao(engine=db_obj)
    web_svc = WebService(route_prefix=route_prefix, is_local=is_local)
    reg_svc = RegService(dao=dao)
    data_svc = DataService(dao=dao, web_svc=web_svc, dir_prefix=dir_prefix)
    ml_svc = MLService(web_svc=web_svc, dao=dao, dir_prefix=dir_prefix)
    rest_svc = RestService(web_svc, reg_svc, data_svc, ml_svc, dao, dir_prefix=dir_prefix, queue_limit=queue_limit,
                           max_tasks=max_tasks)
    services = dict(dao=dao, data_svc=data_svc, ml_svc=ml_svc, reg_svc=reg_svc, web_svc=web_svc, rest_svc=rest_svc)
    website_handler = WebAPI(services=services, js_src=js_src)
    start(host, port, taxii_local=taxii_local, build=conf_build, json_file=attack_dict, app_setup_func=app_setup_func)


if __name__ == '__main__':
    # Help information for the program
    parser = argparse.ArgumentParser(description='Launch the Thread webapp.')
    parser.add_argument('--build-db', action='store_true', help='builds the (PostgreSQL) database')
    parser.add_argument('--schema', help='the schema file to use if --build-db option is used')
    given_args = vars(parser.parse_args())

    if given_args.get('build_db'):
        schema = given_args.get('schema')
        # Import here to avoid PostgreSQL requirements needed for non-PostgreSQL use
        from threadcomponents.database.thread_postgresql import build_db as build_postgresql
        build_postgresql() if schema is None else build_postgresql(schema)
    else:
        main()

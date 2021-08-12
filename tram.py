import os
import sys
import asyncio
import logging
import yaml

import aiohttp_jinja2
import jinja2
from aiohttp import web

from handlers.web_api import WebAPI
from service.data_svc import DataService
from service.web_svc import WebService
from service.reg_svc import RegService
from service.ml_svc import MLService
from service.rest_svc import RestService

from database.dao import Dao

# If we are calling tram from an external source
externally_called = False
# The types of sources for building the database
ONLINE_BUILD_SOURCE = 'taxii-server'
OFFLINE_BUILD_SOURCE = 'local-json'


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
                await data_svc.insert_attack_stix_data()
            except Exception as exc:
                logging.critical('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
                                 'COULD NOT CONNECT TO TAXII SERVERS: {}\nPLEASE UTILIZE THE OFFLINE CAPABILITY FLAG '
                                 '"-FF" FOR OFFLINE DATABASE BUILDING\n'
                                 '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'.format(exc))
                sys.exit()
        elif taxii_local == OFFLINE_BUILD_SOURCE and json_file:
            await data_svc.insert_attack_json_data(json_file)


async def init(host, port):
    """
    Function to initialize the aiohttp app

    :param host: Address to reach webserver on
    :param port: Port to listen on
    :return: nil
    """
    # We want nltk packs downloaded before startup; not run concurrently with startup
    await ml_svc.check_nltk_packs()
    # Before the app starts up, prepare the queue of reports
    await rest_svc.prepare_queue()

    logging.info('server starting: %s:%s' % (host, port))
    webapp_dir = os.path.join('tram', 'webapp') if externally_called else 'webapp'
    logging.info('webapp dir is %s' % webapp_dir)

    app = web.Application(middlewares=[WebAPI.req_handler])
    app.router.add_route('GET', web_svc.app_routes[WebService.HOME_KEY], website_handler.index)
    app.router.add_route('GET', web_svc.app_routes[WebService.EDIT_KEY], website_handler.edit)
    app.router.add_route('GET', web_svc.app_routes[WebService.ABOUT_KEY], website_handler.about)
    app.router.add_route('*', web_svc.app_routes[WebService.REST_KEY], website_handler.rest_api)
    app.router.add_route('GET', web_svc.app_routes[WebService.EXPORT_PDF_KEY], website_handler.pdf_export)
    app.router.add_route('GET', web_svc.app_routes[WebService.EXPORT_NAV_KEY], website_handler.nav_export)
    app.router.add_static(web_svc.app_routes[WebService.STATIC_KEY], os.path.join(webapp_dir, 'theme'))

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(webapp_dir, 'html')))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    # First action after app-initialisation is to resume any reports left in the queue from a previous session
    await rest_svc.check_queue()


def start(host, port, taxii_local=ONLINE_BUILD_SOURCE, build=False, json_file=None):
    """
    Main function to start app
    :param host: Address to reach webserver on
    :param port: Port to listen on
    :param taxii_local: Expects online or offline build_source to specify the build type
    :param build: Defines whether or not a new database will be rebuilt
    :param json_file: Expects a path to the enterprise attack json if the 'offline' build method is called
    :return: nil
    """
    loop = asyncio.get_event_loop()
    loop.create_task(background_tasks(taxii_local=taxii_local, build=build, json_file=json_file))
    loop.run_until_complete(init(host, port))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


def main(external_caller=False):
    global data_svc, externally_called, ml_svc, rest_svc, web_svc, website_handler

    logging.getLogger().setLevel('DEBUG')
    logging.info('Welcome to TRAM')

    externally_called = external_caller
    db_path = os.path.join('database', 'tram.db')
    db_path = os.path.join('tram', db_path) if external_caller else db_path
    config_dir = os.path.join('tram', 'conf') if external_caller else 'conf'
    dao = Dao(db_path)

    with open(os.path.join(config_dir, 'config.yml')) as c:
        config = yaml.safe_load(c)
        conf_build = config['build']
        host = config['host']
        port = config['port']
        taxii_local = config['taxii-local']
        json_file = os.path.join('models', config['json_file'])
        attack_dict = None

        if conf_build:
            if taxii_local == OFFLINE_BUILD_SOURCE and bool(os.path.isfile(json_file)):
                logging.debug('Will build model from static file')
                attack_dict = os.path.abspath(json_file)

    # Start services and initiate main function
    web_svc = WebService(externally_called=external_caller)
    reg_svc = RegService(dao=dao)
    data_svc = DataService(dao=dao, web_svc=web_svc, externally_called=external_caller)
    ml_svc = MLService(web_svc=web_svc, dao=dao, externally_called=external_caller)
    rest_svc = RestService(web_svc, reg_svc, data_svc, ml_svc, dao, externally_called=external_caller)
    services = dict(dao=dao, data_svc=data_svc, ml_svc=ml_svc, reg_svc=reg_svc, web_svc=web_svc, rest_svc=rest_svc)
    website_handler = WebAPI(services=services)
    start(host, port, taxii_local=taxii_local, build=conf_build, json_file=attack_dict)


if __name__ == '__main__':
    main()

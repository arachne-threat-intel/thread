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

externally_called = False

@asyncio.coroutine
async def background_tasks(taxii_local='online', build=False, json_file=None):
    """
    Function to run background tasks at startup
    :param taxii_local: Expects 'online' or 'offline' to specify the build type.
    :param build: Defines whether or not a new database will be rebuilt
    :param json_file: Expects a path to the enterprise attack json if the 'json' build method is called.
    :return: nil
    """
    if build:
        await data_svc.reload_database()
        if taxii_local == 'taxii-server':
            try:
                await data_svc.insert_attack_stix_data()
            except Exception as exc:
                logging.critical('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
                                 'COULD NOT CONNECT TO TAXII SERVERS: {}\nPLEASE UTILIZE THE OFFLINE CAPABILITY FLAG '
                                 '"-FF" FOR OFFLINE DATABASE BUILDING\n'
                                 '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'.format(exc))
                sys.exit()
        elif taxii_local == 'local-json' and json_file:
            await data_svc.insert_attack_json_data(json_file)


@asyncio.coroutine
async def init(host, port):
    """
    Function to initialize the aiohttp app

    :param host: Address to reach webserver on
    :param port: Port to listen on
    :return: nil
    """
    logging.info('server starting: %s:%s' % (host, port))
    app = web.Application()

    app.router.add_route('GET', '/', website_handler.index)
    app.router.add_route('GET', '/edit/{file}', website_handler.edit)
    app.router.add_route('GET', '/about', website_handler.about)
    app.router.add_route('*', '/rest', website_handler.rest_api)
    app.router.add_route('GET', '/export/pdf/{file}', website_handler.pdf_export)
    app.router.add_route('GET', '/export/nav/{file}', website_handler.nav_export)
    webapp_dir = os.path.join('tram', 'webapp') if externally_called else 'webapp'
    logging.info('webapp dir is %s' % (webapp_dir))
    app.router.add_static('/theme/', os.path.join(webapp_dir, 'theme'))

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(webapp_dir, 'html')))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()


def start(host, port, taxii_local=False, build=False, json_file=None):
    """
    Main function to start app
    :param host: Address to reach webserver on
    :param port: Port to listen on
    :param on_off: Expects 'online' or 'offline' to specify the build type.
    :param json_file: Expects a path to the enterprise attack json if the 'offline' build method is called.
    :return: nil
    """
    loop = asyncio.get_event_loop()
    loop.create_task(background_tasks(taxii_local=taxii_local, build=build, json_file=json_file))
    loop.create_task(ml_svc.check_nltk_packs())
    loop.run_until_complete(init(host, port))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


def main(external_caller=True):
    global website_handler, data_svc, ml_svc, externally_called

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
            if taxii_local == 'local-json' and bool(os.path.isfile(json_file)):
                logging.debug('Will build model from static file')
                attack_dict = os.path.abspath(json_file)

    # Start services and initiate main function
    web_svc = WebService()
    reg_svc = RegService(dao=dao)
    data_svc = DataService(dao=dao, web_svc=web_svc, externally_called=external_caller)
    ml_svc = MLService(web_svc=web_svc, dao=dao)
    rest_svc = RestService(web_svc, reg_svc, data_svc, ml_svc, dao, externally_called=external_caller)
    services = dict(dao=dao, data_svc=data_svc, ml_svc=ml_svc, reg_svc=reg_svc, web_svc=web_svc, rest_svc=rest_svc)
    website_handler = WebAPI(services=services)
    start(host, port, taxii_local=taxii_local, build=conf_build, json_file=attack_dict)


if __name__ == '__main__':
    main(external_caller=False)

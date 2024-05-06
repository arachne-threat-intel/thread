# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import logging

from aiohttp.web_exceptions import HTTPException
from aiohttp_jinja2 import template, web
from aiohttp_security import authorized_userid
from aiohttp_session import get_session
from datetime import datetime
from urllib.parse import quote

# The config options to load JS dependencies
ONLINE_JS_SRC = 'js-online-src'
OFFLINE_JS_SRC = 'js-local-src'
# Key for a flag checking when a user has accepted the cookie notice
ACCEPT_COOKIE = 'accept_cookie_notice'


class WebAPI:
    """A class to handle receiving requests via the website."""
    def __init__(self, services, report_exporter, js_src=None):
        self.dao = services['dao']
        self.data_svc = services['data_svc']
        self.web_svc = services['web_svc']
        self.ml_svc = services['ml_svc']
        self.reg_svc = services['reg_svc']
        self.rest_svc = services['rest_svc']
        self.report_statuses = self.rest_svc.get_status_enum()
        self.is_local = self.web_svc.is_local
        self.report_exporter = report_exporter
        js_src_config = js_src if js_src in [ONLINE_JS_SRC, OFFLINE_JS_SRC] else ONLINE_JS_SRC
        self.BASE_PAGE_DATA = dict(about_url=self.web_svc.get_route(self.web_svc.ABOUT_KEY),
                                   home_url=self.web_svc.get_route(self.web_svc.HOME_KEY),
                                   how_it_works_url=self.web_svc.get_route(self.web_svc.HOW_IT_WORKS_KEY),
                                   what_to_submit_url=self.web_svc.get_route(self.web_svc.WHAT_TO_SUBMIT_KEY),
                                   rest_url=self.web_svc.get_route(self.web_svc.REST_KEY),
                                   static_url=self.web_svc.get_route(self.web_svc.STATIC_KEY),
                                   js_src_online=js_src_config == ONLINE_JS_SRC, is_local=self.is_local)
        self.attack_dropdown_list = []
        self.cat_dropdown_list = []
        self.web_svc.keyword_dropdown_list = []

    async def set_attack_dropdown_list(self):
        """Function to set the attack-dropdown-list used to add/reject attacks in a report."""
        self.attack_dropdown_list = await self.data_svc.get_techniques(get_parent_info=True)

    async def set_keyword_dropdown_list(self):
        """Function to set the keyword-dropdown-list used to select aggressors and victims in a report."""
        # I was unable to order the APTs using a single UNION query which kept the order of the queries below
        # Two queries to ensure APT1, APT10, APT11, ... APT2, APT20, ... ordering does not happen
        apt_query = "SELECT name FROM keywords WHERE name LIKE 'APT%' ORDER BY LENGTH(name), name"
        r1 = await self.dao.raw_select(apt_query, single_col=True)
        non_apt_query = "SELECT name FROM keywords WHERE name NOT LIKE 'APT%' ORDER BY name"
        r2 = await self.dao.raw_select(non_apt_query, single_col=True)
        self.web_svc.keyword_dropdown_list = r1 + r2

    async def pre_launch_init(self):
        """Function to call any required methods before the app is initialised and launched."""
        # We want nltk packs downloaded before startup; not run concurrently with startup
        await self.ml_svc.check_nltk_packs()
        # Before the app starts up, prepare the queue of reports
        await self.rest_svc.prepare_queue()
        # We want the list of attacks, categories and keywords ready before the app starts
        await self.set_attack_dropdown_list()
        self.cat_dropdown_list = await self.data_svc.get_all_categories()
        await self.set_keyword_dropdown_list()
        # We want column names ready
        await self.dao.db.initialise_column_names()

    async def fetch_and_update_attack_data(self):
        """Function to fetch and update the attack data."""
        # If updates occurred when fetching the attack-data, we need to update the dropdown list
        updates = await self.rest_svc.fetch_and_update_attack_data()
        if updates:
            await self.set_attack_dropdown_list()

    async def fetch_and_update_keywords(self):
        """Function to fetch and update the list of keywords."""
        logging.info('UPDATE FROM R-STONE: START')
        # If updates occurred when fetching the keywords, we need to update the dropdown list
        updates = await self.data_svc.insert_keyword_json_data()
        if updates:
            await self.set_keyword_dropdown_list()
        logging.info('UPDATE FROM R-STONE: END')

    async def add_base_page_data(self, request, data=None):
        """Function to add the base page data to context data given a request."""
        # If there is no data dictionary to update, there is nothing to do
        if not isinstance(data, dict):
            return
        # Update data with the base page data
        data.update(self.BASE_PAGE_DATA)
        data.update(current_year=datetime.now().strftime('%Y'))
        # Non-local sessions include cookies, update context data for this
        if not self.is_local:
            # Check request if the cookie banner has been dismissed
            session = await get_session(request)
            data.update(hide_cookie_notice=session.get(ACCEPT_COOKIE, False),
                        cookie_url=self.web_svc.get_route(self.web_svc.COOKIE_KEY))

    @staticmethod
    @web.middleware
    async def req_handler(request: web.Request, handler):
        """Function to intercept an application's requests and tweak the responses."""
        # Can't delete the Server header so leave as blank or junk
        server, server_msg = 'Server', 'Squeak, squeakin\', squeakity'
        try:
            # Get the response from the request as normal
            response: web.Response = await handler(request)
        except HTTPException as error_resp:
            # If an exception occurred, override the server response header
            try:
                error_resp.headers[server] = server_msg
            # If this couldn't be done, log it so it can be re-tested to see how the header can be overridden
            except (AttributeError, KeyError):
                logging.warning('SERVER RESP HEADER exposed; %s | %s' % (str(request), str(error_resp)))
            # Despite the exception, we want the error raised so the app can receive it
            finally:
                raise error_resp
        # If a response was retrieved, override the server response header and finally return the response
        response.headers[server] = server_msg
        return response

    async def accept_cookies(self, request):
        # There's no content expected for this request
        response = web.HTTPNoContent()
        # There's nothing to do (no cookies to accept) for local-use
        if self.is_local:
            return response
        # Only strictly necessary cookies are being used so we are not expecting rejecting cookies
        # nor do we need to store user's response. Just update the session flag to prevent displaying notice again.
        session = await get_session(request)
        session[ACCEPT_COOKIE] = True
        # Default response content-type triggers a browser download; change this
        response.content_type = 'text/html'
        return response

    @template('about.html')
    async def about(self, request):
        page_data = dict(title='Using Thread')
        await self.add_base_page_data(request, data=page_data)
        return page_data

    @template('what-to-submit.html')
    async def what_to_submit(self, request):
        page_data = dict(title='What Can I Submit?')
        await self.add_base_page_data(request, data=page_data)
        return page_data

    @template('how-it-works.html')
    async def how_it_works(self, request):
        page_data = dict(title='How Thread Works')
        await self.add_base_page_data(request, data=page_data)
        return page_data

    @template('index.html')
    async def index(self, request):
        # Dictionaries for the template data
        page_data, template_data = dict(), dict()
        # Add base page data to overall template data
        await self.add_base_page_data(request, data=template_data)
        # The token used for this session
        token, verified_token = None, None
        # Adding user details if this is not a local session
        if not self.is_local:
            token = await authorized_userid(request)
            if token:
                username, verified_token = await self.web_svc.get_current_arachne_user(request)
                template_data.update(username=username)
        # For each report status, get the reports for the index page
        for status in self.report_statuses:
            is_complete_status = status.value == self.report_statuses.COMPLETED.value
            # Properties for all statuses when displayed on the index page
            page_data[status.value] = \
                dict(display_name=status.display_name, allow_delete=True,
                     error_msg='Sorry, an error occurred with this report and may appear different than intended.',
                     analysis_button='View Analysis' if is_complete_status else 'Analyse')
            # If the status is 'queue', obtain errored reports separately so we can provide info without these
            if status.value == self.report_statuses.QUEUE.value:
                pending = await self.data_svc.status_grouper(
                    status.value, criteria=dict(error=self.dao.db_false_val, token=verified_token))
                errored = await self.data_svc.status_grouper(
                    status.value, criteria=dict(error=self.dao.db_true_val, token=verified_token))
                page_data[status.value]['reports'] = pending + errored
                if self.rest_svc.QUEUE_LIMIT:
                    template_data['queue_set'] = 1
                    # Extra info for queued reports if a queue limit was set
                    queue_ratio = (len(pending), self.rest_svc.QUEUE_LIMIT)
                    # Add to the display name the fraction of the queue limit used
                    page_data[status.value]['display_name'] += ' (%s/%s)' % queue_ratio
                    # Also add a fuller sentence describing the fraction
                    page_data[status.value]['column_info'] = '%s report(s) pending in Queue out of MAX %s' % queue_ratio
                # Queued reports can't be deleted (unless errored)
                page_data[status.value]['allow_delete'] = False
                # There is no analysis button for queued reports
                del page_data[status.value]['analysis_button']
                # Queued reports with errors have an error because the contents can't be viewed: update error message
                page_data[status.value]['error_msg'] = 'Sorry, the contents of this report could not be retrieved.'
            # Else proceed to obtain the reports for this status as normal
            else:
                page_data[status.value]['reports'] = \
                    await self.data_svc.status_grouper(status.value, criteria=dict(token=verified_token))
            # Allow only mid-review reports to be rollbacked
            page_data[status.value]['allow_rollback'] = status.value == self.report_statuses.IN_REVIEW.value
        # Update overall template data and return
        template_data.update(reports_by_status=page_data)
        return template_data

    async def rest_api(self, request):
        """
        Function to handle rest api calls
        :param request: json data with rest request
        :return: json response
        """
        data = dict(await request.json())
        try:
            index = data.pop('index')
            options = dict(
                POST=dict(
                    add_attack=lambda d: self.rest_svc.add_attack(request=request, criteria=d),
                    reject_attack=lambda d: self.rest_svc.reject_attack(request=request, criteria=d),
                    set_status=lambda d: self.rest_svc.set_status(request=request, criteria=d),
                    insert_report=lambda d: self.rest_svc.insert_report(request=request, criteria=d),
                    insert_csv=lambda d: self.rest_svc.insert_csv(request=request, criteria=d),
                    remove_sentence=lambda d: self.rest_svc.remove_sentence(request=request, criteria=d),
                    delete_report=lambda d: self.rest_svc.delete_report(request=request, criteria=d),
                    rollback_report=lambda d: self.rest_svc.rollback_report(request=request, criteria=d),
                    sentence_context=lambda d: self.rest_svc.sentence_context(request=request, criteria=d),
                    confirmed_attacks=lambda d: self.rest_svc.confirmed_attacks(request=request, criteria=d),
                    update_report_dates=lambda d: self.rest_svc.update_report_dates(request=request, criteria=d),
                    update_attack_time=lambda d: self.rest_svc.update_attack_time(request=request, criteria=d),
                    set_report_keywords=lambda d: self.rest_svc.set_report_keywords(request=request, criteria=d),
                    suggest_indicator_of_compromise=lambda d: self.rest_svc.suggest_ioc(request=request, criteria=d),
                    suggest_and_save_ioc=lambda d: self.rest_svc.suggest_and_save_ioc(request=request, criteria=d),
                    add_indicator_of_compromise=lambda d: self.rest_svc.update_ioc(request=request, criteria=d,
                                                                                   adding=True),
                    update_indicator_of_compromise=lambda d: self.rest_svc.update_ioc(request=request, criteria=d),
                    remove_indicator_of_compromise=lambda d: self.rest_svc.update_ioc(request=request, criteria=d,
                                                                                      deleting=True),
                ))
            method = options[request.method][index]
        except KeyError:
            return web.json_response(None, status=404)
        output = await method(data)
        status = 200
        if (output is not None) and (not isinstance(output, dict)):
            pass
        elif (output is None) or (output.get('success') and not output.get('alert_user')):
            status = 204
        elif output.get('ignored'):
            status = 202
        elif output.get('error'):
            status = 500
        return web.json_response(output, status=status)

    @template('columns.html')
    async def edit(self, request):
        """
        Function to load a report for editing
        :param request: The title of the report information
        :return: dictionary of report data
        """
        # Dictionary for the template data with the base page data included
        template_data = dict()
        await self.add_base_page_data(request, data=template_data)
        # The 'file' property is already unquoted despite a quoted string used in the URL
        report_title = request.match_info.get(self.web_svc.REPORT_PARAM)
        title_quoted = quote(report_title, safe='')
        report = await self.data_svc.get_report_by_title(report_title=report_title, add_expiry_bool=(not self.is_local))
        try:
            # Ensure a valid report title has been passed in the request
            report_id, report_status = report[0]['uid'], report[0]['current_status']
        except (KeyError, IndexError):
            raise web.HTTPNotFound()
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'view', context=dict(report=report[0]))
        # A queued report would pass the above check but be blank; raise an error instead
        if report_status not in [self.report_statuses.NEEDS_REVIEW.value, self.report_statuses.IN_REVIEW.value,
                                 self.report_statuses.COMPLETED.value]:
            raise web.HTTPNotFound()
        # Proceed to gather the data for the template
        sentences = await self.data_svc.get_report_sentences(report_id)
        categories = await self.data_svc.get_report_categories_for_display(report_id, include_keynames=True)
        keywords = await self.data_svc.get_report_aggressors_victims(report_id)
        indicators_of_compromise = await self.data_svc.get_report_sentence_indicators_of_compromise(report_id)
        for sentence in sentences:
            sentence['is_ioc'] = any(ioc['sentence_id'] == sentence['uid'] for ioc in indicators_of_compromise)
        original_html = await self.dao.get('original_html', equal=dict(report_uid=report_id),
                                           order_by_asc=dict(elem_index=1))
        final_html = await self.web_svc.build_final_html(original_html, sentences)
        pdf_link = self.web_svc.get_route(self.web_svc.EXPORT_PDF_KEY, param=title_quoted)
        nav_link = self.web_svc.get_route(self.web_svc.EXPORT_NAV_KEY, param=title_quoted)
        # Add some help-text
        completed_info, private_info, sen_limit_help = None, None, None
        is_completed = int(report_status == self.report_statuses.COMPLETED.value)
        if report[0]['token']:
            private_info = 'This is a private report. If this page becomes unresponsive, please refresh or ' \
                           'visit the Arachne site to check your session has not expired.'
        if is_completed:
            completed_info = 'This is a <b>completed</b> report. You can still click on sentences to view confirmed ' \
                + 'techniques. You can also click the Export PDF button to generate a PDF of this completed report.'
            if not self.is_local:
                completed_info += '<br><br><b>Completed reports will expire 24 hours after completion.</b>'
        if self.rest_svc.SENTENCE_LIMIT:
            sen_limit_help = 'Reports are currently capped to the first %s sentences.' % self.rest_svc.SENTENCE_LIMIT
        # Get the list of sentences with techniques that need to be confirmed
        unchecked = await self.data_svc.get_unconfirmed_undated_attack_count(report_id=report_id, return_detail=True)
        # Update overall template data and return
        template_data.update(
            file=report_title,
            title=report[0]['title'],
            title_quoted=title_quoted,
            final_html=final_html,
            sentences=sentences,
            sentence_limit_helptext=sen_limit_help,
            attack_uids=self.attack_dropdown_list,
            original_html=original_html,
            pdf_link=pdf_link,
            nav_link=nav_link,
            unchecked=unchecked,
            completed_help_text=completed_info,
            private_help_text=private_info,
            completed=is_completed,
            categories=categories,
            category_list=self.cat_dropdown_list,
            group_list=self.web_svc.keyword_dropdown_list,
            aggressor_groups=keywords['aggressors']['groups'],
            aggressor_regions=keywords['aggressors']['region_ids'],
            aggressor_countries=keywords['aggressors']['country_codes'],
            victim_regions=keywords['victims']['region_ids'],
            victim_countries=keywords['victims']['country_codes'],
            region_list=self.data_svc.region_dict,
            country_list=self.data_svc.country_dict,
            country_region_list=self.data_svc.country_region_dict,
            vic_cat_all=keywords['victims']['categories_all'],
            vic_countries_all=keywords['victims']['countries_all'],
        )
        # Prepare the date fields to be interpreted by the front-end
        for report_date in ['date_written', 'start_date', 'end_date']:
            saved_date = report[0].get(report_date + '_str')  # field is returned under field_str
            if saved_date:
                template_data[report_date] = saved_date
        start_date, end_date = template_data.get('start_date'), template_data.get('end_date')
        if start_date and end_date and (start_date == end_date):
            template_data.update(same_dates=True)
        return template_data

    async def nav_export(self, request):
        """
        Function to export confirmed sentences in layer json format
        :param request: The title of the report information
        :return: the layer json
        """
        json_str = await self.report_exporter.nav_export(request)
        return web.json_response(json_str)

    async def pdf_export(self, request):
        """
        Function to export report in PDF format
        :param request: The title of the report information
        :return: response status of function
        """
        pdfmake_data = await self.report_exporter.pdf_export(request)
        return web.json_response(pdfmake_data)

    async def rebuild_ml(self, request):
        """
        This is a new api function to force a rebuild of the ML models.
        This is intended to be kicked off in the background at some point.
        :param request: uh, nothing?
        :return: status of rebuild
        """
        # get techniques from database
        tech_data = await self.data_svc.get_techniques()
        techniques = {}
        for row in tech_data:
            # skip software for now
            if 'tool' in row['tid'] or 'malware' in row['tid']:
                continue
            else:
                # query for true positives
                true_pos = await self.dao.get('true_positives', dict(attack_uid=row['uid']))
                tp = []
                for t in true_pos:
                    tp.append(t['true_positive'])
                # query for false negatives and false positives
                false_neg = await self.dao.get('false_negatives', dict(attack_uid=row['uid']))
                false_positives = await self.dao.get('false_positives', dict(attack_uid=row['uid']))
                for f in false_neg:
                    tp.append(f['false_negative'])
                fp = []
                for fps in false_positives:
                    fp.append(fps['false_positive'])

                techniques[row['uid']] = {'id': row['tid'], 'name': row['name'], 'similar_words': [],
                                          'example_uses': tp, 'false_positives': fp}

        list_of_legacy, list_of_techs = self.data_svc.ml_reg_split(techniques)
        self.ml_svc.build_pickle_file(list_of_techs, techniques, force=True)

        return {'text': 'ML Rebuilt!'}

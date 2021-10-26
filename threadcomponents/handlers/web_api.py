# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import json
import logging

from aiohttp.web_exceptions import HTTPException
from aiohttp_jinja2 import template, web
from aiohttp_session import get_session
from urllib.parse import quote

# The config options to load JS dependencies
ONLINE_JS_SRC = 'js-online-src'
OFFLINE_JS_SRC = 'js-local-src'
# Key for a flag checking when a user has accepted the cookie notice
ACCEPT_COOKIE = 'accept_cookie_notice'


def sanitise_filename(filename=''):
    """Function to produce a string which is filename-friendly."""
    # Preserve any quotes by replacing all with ' (which is accepted by Windows OS unlike " which is not)
    temp_fn = filename.replace('"', '\'').replace('’', '\'').replace('“', '\'').replace('”', '\'')
    # Join all characters (replacing invalid ones with _) to produce final filename
    return ''.join([x if (x.isalnum() or x in '-\'') else '_' for x in temp_fn])


class WebAPI:
    def __init__(self, services, js_src):
        self.dao = services.get('dao')
        self.data_svc = services['data_svc']
        self.web_svc = services['web_svc']
        self.ml_svc = services['ml_svc']
        self.reg_svc = services['reg_svc']
        self.rest_svc = services['rest_svc']
        self.report_statuses = self.rest_svc.get_status_enum()
        self.is_local = self.web_svc.is_local
        js_src_config = js_src if js_src in [ONLINE_JS_SRC, OFFLINE_JS_SRC] else ONLINE_JS_SRC
        self.BASE_PAGE_DATA = dict(about_url=self.web_svc.get_route(self.web_svc.ABOUT_KEY),
                                   home_url=self.web_svc.get_route(self.web_svc.HOME_KEY),
                                   rest_url=self.web_svc.get_route(self.web_svc.REST_KEY),
                                   static_url=self.web_svc.get_route(self.web_svc.STATIC_KEY),
                                   js_src_online=js_src_config == ONLINE_JS_SRC, is_local=self.is_local)
        self.attack_dropdown_list = []

    async def pre_launch_init(self):
        """Function to call any required methods before the app is initialised and launched."""
        # We want nltk packs downloaded before startup; not run concurrently with startup
        await self.ml_svc.check_nltk_packs()
        # Before the app starts up, prepare the queue of reports
        await self.rest_svc.prepare_queue()
        # We want the list of attacks ready before the app starts
        self.attack_dropdown_list = await self.data_svc.get_techniques(get_parent_info=True)
        # We want column names ready
        await self.dao.db.initialise_column_names()

    @staticmethod
    def respond_error(message=None):
        """Function to produce an error JSON response."""
        if message is None:
            return web.json_response(None, status=500)
        else:
            return web.json_response(text=message, status=500)

    async def add_base_page_data(self, request, data=None):
        """Function to add the base page data to context data given a request."""
        # If there is no data dictionary to update, there is nothing to do
        if type(data) != dict:
            return
        # Update data with the base page data
        data.update(self.BASE_PAGE_DATA)
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
        page_data = dict(title='About')
        await self.add_base_page_data(request, data=page_data)
        return page_data

    @template('index.html')
    async def index(self, request):
        # Dictionaries for the template data
        page_data, template_data = dict(), dict()
        # Add base page data to overall template data
        await self.add_base_page_data(request, data=template_data)
        # The token used for this session
        token = None
        # Adding user details if this is not a local session
        if not self.is_local:
            token = await self.web_svc.get_current_token(request)
            username = await self.web_svc.get_username_from_token(request, token)
            template_data.update(token=token, username=username)
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
                    status.value, criteria=dict(error=self.dao.db_false_val, token=token))
                errored = await self.data_svc.status_grouper(
                    status.value, criteria=dict(error=self.dao.db_true_val, token=token))
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
                    await self.data_svc.status_grouper(status.value, criteria=dict(token=token))
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
                    confirmed_attacks=lambda d: self.rest_svc.confirmed_attacks(request=request, criteria=d)
                ))
            method = options[request.method][index]
        except KeyError:
            return self.respond_error()
        output = await method(data)
        status = 200
        if output is not None and type(output) != dict:
            pass
        elif output is None or (output.get('success') and not output.get('alert_user')):
            status = 204
        elif output.get('ignored'):
            status = 202
        elif output.get('error'):
            status = 500
        return web.json_response(output, status=status)

    @template('columns.html')
    async def edit(self, request):
        """
        Function to edit report
        :param request: The title of the report information
        :return: dictionary of report data
        """
        # Dictionary for the template data with the base page data included
        template_data = dict()
        await self.add_base_page_data(request, data=template_data)
        # The 'file' property is already unquoted despite a quoted string used in the URL
        report_title = request.match_info.get(self.web_svc.REPORT_PARAM)
        title_quoted = quote(report_title, safe='')
        report = await self.dao.get('reports', dict(title=report_title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id = report[0]['uid']
        except (KeyError, IndexError):
            return self.respond_error(message='Invalid URL')
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'edit', context=dict(report=report[0]))
        # A queued report would pass the above check but be blank; raise an error instead
        if report[0]['current_status'] == self.report_statuses.QUEUE.value:
            return self.respond_error(message='Invalid URL')
        # Proceed to gather the data for the template
        sentences = await self.data_svc.get_report_sentences(report_id)
        original_html = await self.dao.get('original_html', equal=dict(report_uid=report_id),
                                           order_by_asc=dict(elem_index=1))
        final_html = await self.web_svc.build_final_html(original_html, sentences)
        pdf_link = self.web_svc.get_route(self.web_svc.EXPORT_PDF_KEY, param=title_quoted)
        nav_link = self.web_svc.get_route(self.web_svc.EXPORT_NAV_KEY, param=title_quoted)
        # Update overall template data and return
        template_data.update(
            file=report_title, title=report[0]['title'], title_quoted=title_quoted, final_html=final_html,
            sentences=sentences, attack_uids=self.attack_dropdown_list, original_html=original_html, pdf_link=pdf_link,
            nav_link=nav_link, completed=int(report[0]['current_status'] == self.report_statuses.COMPLETED.value)
        )
        return template_data

    async def nav_export(self, request):
        """
        Function to export confirmed sentences in layer json format
        :param request: The title of the report information
        :return: the layer json
        """        
        # Get the report from the database
        report_title = request.match_info.get(self.web_svc.REPORT_PARAM)
        report = await self.dao.get('reports', dict(title=report_title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id, report_status = report[0]['uid'], report[0]['current_status']
        except (KeyError, IndexError):
            return self.respond_error()
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'nav-export', context=dict(report=report[0]))
        # A queued report would pass the above checks but be blank; raise an error instead
        if report_status not in [self.report_statuses.NEEDS_REVIEW.value, self.report_statuses.IN_REVIEW.value,
                                 self.report_statuses.COMPLETED.value]:
            return self.respond_error()

        # Create the layer name and description
        enterprise_layer_description = f"Enterprise techniques used by '{report_title}', ATT&CK"
        version = '1.0'
        if version:  # add version number if it exists
            enterprise_layer_description += f" v{version}"

        # Enterprise navigator layer
        enterprise_layer = {
            'filename': sanitise_filename(report_title), 'name': report_title, 'domain': 'mitre-enterprise',
            'description': enterprise_layer_description, 'version': '2.2', 'techniques': [],
            # white for non-used, blue for used
            'gradient': {'colors': ['#ffffff', '#66b1ff'], 'minValue': 0, 'maxValue': 1},
            'legendItems': [{'label': f'used by {report_title}', 'color': '#66b1ff'}]
        }

        # Get confirmed techniques for the report from the database
        techniques = await self.data_svc.get_confirmed_techniques_for_nav_export(report_id)

        # Append techniques to enterprise layer
        for technique in techniques:
            enterprise_layer['techniques'].append(technique)
            
        # Return the layer JSON in the response
        layer = json.dumps(enterprise_layer)
        return web.json_response(layer)

    async def pdf_export(self, request):
        """
        Function to export report in PDF format
        :param request: The title of the report information
        :return: response status of function
        """
        # Get the report and its sentences
        title = request.match_info.get(self.web_svc.REPORT_PARAM)
        report = await self.dao.get('reports', dict(title=title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id, report_status, report_url = report[0]['uid'], report[0]['current_status'], report[0]['url']
        except (KeyError, IndexError):
            return self.respond_error()
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'pdf-export', context=dict(report=report[0]))
        # A queued report would pass the above checks but be blank; raise an error instead
        if report_status not in [self.report_statuses.NEEDS_REVIEW.value, self.report_statuses.IN_REVIEW.value,
                                 self.report_statuses.COMPLETED.value]:
            return self.respond_error()
        # Continue with the method and retrieve the report's sentences
        sentences = await self.data_svc.get_report_sentences_with_attacks(report_id=report_id)

        dd = dict()
        dd['content'] = []
        # The styles for this pdf - hyperlink styling needed to be added manually
        dd['styles'] = dict(header=dict(fontSize=25, bold=True, alignment='center'), bold=dict(bold=True),
                            sub_header=dict(fontSize=15, bold=True), url=dict(color='blue', decoration='underline'))
        # Document MetaData Info
        # See https://pdfmake.github.io/docs/document-definition-object/document-medatadata/
        dd['info'] = dict()
        dd['info']['title'] = sanitise_filename(title)
        dd['info']['creator'] = report_url

        # Extra content if this report hasn't been completed: highlight it's a draft
        if report_status != self.report_statuses.COMPLETED.value:
            dd['content'].append(dict(text='DRAFT: Please note this report is still being analysed. '
                                           'Techniques listed here may change later on.', style='sub_header'))
            dd['content'].append(dict(text='\n'))  # Blank line before report's title
            dd['watermark'] = dict(text='DRAFT', opacity=0.3, bold=True, angle=70)

        # Table for found attacks
        table = {'body': []}
        table['body'].append(['ID', 'Name', 'Identified Sentence'])
        # Add the text to the document
        dd['content'].append(dict(text=title, style='header'))  # begin with title of document
        dd['content'].append(dict(text='\n'))  # Blank line after title
        dd['content'].append(dict(text='URL:', style='bold'))  # State report's source
        dd['content'].append(dict(text=report_url, style='url'))
        dd['content'].append(dict(text='\n'))  # Blank line after URL
        seen_sentences = set()  # set to prevent duplicate sentences being exported
        for sentence in sentences:
            sen_id, sen_text = sentence['uid'], sentence['text']
            if sen_id not in seen_sentences:
                dd['content'].append(sen_text)
                seen_sentences.add(sen_id)
            if sentence['attack_tid'] and sentence['active_hit']:
                # Append any attack for this sentence to the table; prefix parent-tech for any sub-technique
                tech_name, parent_tech = sentence['attack_technique_name'], sentence.get('attack_parent_name')
                tech_name = "%s: %s" % (parent_tech, tech_name) if parent_tech else tech_name
                table['body'].append([sentence['attack_tid'], tech_name, sen_text])

        # Append table to the end
        dd['content'].append({'table': table})
        return web.json_response(dd)

    async def rebuild_ml(self, request):
        """
        This is a new api function to force a rebuild of the ML models. This is intended to be kicked off in the background at some point
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

        # query for true negatives
        true_negatives = []
        true_negs = await self.dao.get('true_negatives')
        for i in true_negs:
            true_negatives.append(i['sentence'])
        list_of_legacy, list_of_techs = await self.data_svc.ml_reg_split(techniques)
        self.ml_svc.build_pickle_file(list_of_techs, techniques, true_negatives, force=True)

        return {'text': 'ML Rebuilt!'}

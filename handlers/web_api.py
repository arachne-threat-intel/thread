import json

from aiohttp_jinja2 import render_template, web
from urllib.parse import quote

# The different types of templates Tram is using
ABOUT, INDEX, EDIT = 'about', 'index', 'edit'
TEMPLATES = {ABOUT: 'about.html', INDEX: 'index.html', EDIT: 'columns.html'}
# Obfuscate server in response headers
SERVER = 'Server'
SERVER_VAL = 'Squeak, squeakin\', squeakity'


def sanitise_filename(filename=''):
    """Function to produce a string which is filename-friendly."""
    # Preserve any quotes by replacing all with ' (which is accepted by Windows OS unlike " which is not)
    temp_fn = filename.replace('"', '\'').replace('’', '\'').replace('“', '\'').replace('”', '\'')
    # Join all characters (replacing invalid ones with _) to produce final filename
    return ''.join([x if (x.isalnum() or x in '-\'') else '_' for x in temp_fn])


class WebReqHandler(web.View):
    async def get(self, html: str, data=None):
        """Function to render a given template (html) optionally with data."""
        response = render_template(html, self.request, data)
        # Can't delete the Server header so leave as blank or junk
        response.headers[SERVER] = SERVER_VAL
        return response


class WebAPI:
    def __init__(self, services):
        self.dao = services.get('dao')
        self.data_svc = services['data_svc']
        self.web_svc = services['web_svc']
        self.ml_svc = services['ml_svc']
        self.reg_svc = services['reg_svc']
        self.rest_svc = services['rest_svc']
        self.report_statuses = self.rest_svc.get_status_enum()

    @staticmethod
    def respond_error(message=None):
        """Function to produce an error JSON response."""
        if message is None:
            return web.json_response(None, status=500, headers={SERVER: SERVER_VAL})
        else:
            return web.json_response(text=message, status=500, headers={SERVER: SERVER_VAL})

    @staticmethod
    def respond_data(data=None, status=200):
        """Function to produce a JSON response with data."""
        return web.json_response(data, status=status, headers={SERVER: SERVER_VAL})

    async def about(self, request):
        return await WebReqHandler(request=request).get(html=TEMPLATES[ABOUT])

    async def index(self, request):
        page_data = dict()
        # For each report status, get the reports for the index page
        for status in self.report_statuses:
            is_complete_status = status.value == self.report_statuses.COMPLETED.value
            # Properties for all statuses when displayed on the index page
            page_data[status.value] = dict(display_name=status.display_name, allow_delete=True,
                                           analysis_button='View Analysis' if is_complete_status else 'Analyse')
            # If the status is 'queue', obtain errored reports separately so we can provide info without these
            if status.value == self.report_statuses.QUEUE.value:
                pending = await self.data_svc.status_grouper(status.value, criteria=dict(error=0))
                errored = await self.data_svc.status_grouper(status.value, criteria=dict(error=1))
                page_data[status.value]['reports'] = pending + errored
                # Extra info for queued reports
                queue_ratio = (len(pending), self.rest_svc.QUEUE_LIMIT)
                # Add to the display name the fraction of the queue limit used
                page_data[status.value]['display_name'] += ' (%s/%s)' % queue_ratio
                # Also add a fuller sentence describing the fraction
                page_data[status.value]['column_info'] = '%s report(s) pending in Queue out of MAX %s' % queue_ratio
                # Queued reports can't be deleted (unless errored)
                page_data[status.value]['allow_delete'] = False
                # There is no analysis button for queued reports
                del page_data[status.value]['analysis_button']
            # Else proceed to obtain the reports for this status as normal
            else:
                page_data[status.value]['reports'] = await self.data_svc.status_grouper(status.value)
        return await WebReqHandler(request=request).get(html=TEMPLATES[INDEX], data=dict(reports_by_status=page_data))

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
                    add_attack=lambda d: self.rest_svc.add_attack(criteria=d),
                    reject_attack=lambda d: self.rest_svc.reject_attack(criteria=d),
                    set_status=lambda d: self.rest_svc.set_status(criteria=d),
                    insert_report=lambda d: self.rest_svc.insert_report(criteria=d),
                    insert_csv=lambda d: self.rest_svc.insert_csv(criteria=d),
                    remove_sentence=lambda d: self.rest_svc.remove_sentence(criteria=d),
                    delete_report=lambda d: self.rest_svc.delete_report(criteria=d),
                    sentence_context=lambda d: self.rest_svc.sentence_context(criteria=d),
                    confirmed_attacks=lambda d: self.rest_svc.confirmed_attacks(criteria=d)
                ))
            method = options[request.method][index]
        except KeyError:
            return self.respond_error()
        output = await method(data)
        status = 200
        if output is not None and type(output) != dict:
            pass
        elif output is None or output.get('success'):
            status = 204
        elif output.get('ignored'):
            status = 202
        elif output.get('error'):
            status = 500
        return self.respond_data(data=output, status=status)

    async def edit(self, request):
        """
        Function to edit report
        :param request: The title of the report information
        :return: dictionary of report data
        """
        # The 'file' property is already unquoted despite a quoted string used in the URL
        report_title = request.match_info.get('file')
        title_quoted = quote(report_title)
        report = await self.dao.get('reports', dict(title=report_title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id = report[0]['uid']
        except (KeyError, IndexError):
            return self.respond_error(message='Invalid URL')
        # A queued report would pass the above check but be blank; raise an error instead
        if report[0]['current_status'] == self.report_statuses.QUEUE.value:
            return self.respond_error(message='Invalid URL')
        # Proceed to gather the data for the template
        sentences = await self.data_svc.get_report_sentences(report_id)
        attack_uids = await self.data_svc.get_techniques()
        original_html = await self.dao.get('original_html', dict(report_uid=report_id))
        final_html = await self.web_svc.build_final_html(original_html, sentences)
        page_data = dict(file=report_title, title=report[0]['title'], title_quoted=title_quoted, final_html=final_html,
                         sentences=sentences, attack_uids=attack_uids, original_html=original_html,
                         completed=int(report[0]['current_status'] == self.report_statuses.COMPLETED.value))
        return await WebReqHandler(request=request).get(html=TEMPLATES[EDIT], data=page_data)

    async def nav_export(self, request):
        """
        Function to export confirmed sentences in layer json format
        :param request: The title of the report information
        :return: the layer json
        """        
        # Get the report from the database
        report_title = request.match_info.get('file')
        report = await self.dao.get('reports', dict(title=report_title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id, report_status = report[0]['uid'], report[0]['current_status']
        except (KeyError, IndexError):
            return self.respond_error()
        # A queued report would pass the above check but be blank; raise an error instead
        if report_status == self.report_statuses.QUEUE.value:
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
        techniques = await self.data_svc.get_confirmed_techniques_for_report(report_id)

        # Append techniques to enterprise layer
        for technique in techniques:
            enterprise_layer['techniques'].append(technique)
            
        # Return the layer JSON in the response
        layer = json.dumps(enterprise_layer)
        return self.respond_data(data=layer)

    async def pdf_export(self, request):
        """
        Function to export report in PDF format
        :param request: The title of the report information
        :return: response status of function
        """
        # Get the report and its sentences
        title = request.match_info.get('file')
        report = await self.dao.get('reports', dict(title=title))
        try:
            # Ensure a valid report title has been passed in the request
            report_id, report_status, report_url = report[0]['uid'], report[0]['current_status'], report[0]['url']
        except (KeyError, IndexError):
            return self.respond_error()
        # A queued report would pass the above check but be blank; raise an error instead
        if report_status == self.report_statuses.QUEUE.value:
            return self.respond_error()
        # Continue with the method and retrieve the report's sentences
        sentences = await self.data_svc.get_report_sentences_with_attacks(report_id=report_id)

        dd = dict()
        dd['content'] = []
        dd['styles'] = dict(header=dict(fontSize=25, bold=True, alignment='center'),
                            sub_header=dict(fontSize=15, bold=True))
        # Document MetaData Info
        # See https://pdfmake.github.io/docs/document-definition-object/document-medatadata/
        dd['info'] = dict()
        dd['info']['title'] = sanitise_filename(title)
        dd['info']['creator'] = report_url

        # Extra content if this report hasn't been completed: highlight it's a draft
        if report_status != self.report_statuses.COMPLETED.value:
            dd['content'].append(dict(text='DRAFT: Please note this report is still being analysed. '
                                           'Techniques listed here may change later on.', style='sub_header'))
            dd['watermark'] = dict(text='DRAFT', opacity=0.3, bold=True, angle=70)

        # Table for found attacks
        table = {'body': []}
        table['body'].append(['ID', 'Name', 'Identified Sentence'])
        # Add the text to the document
        dd['content'].append(dict(text=title, style='header'))  # begin with title of document
        seen_sentences = set()  # set to prevent duplicate sentences being exported
        for sentence in sentences:
            sen_id, sen_text = sentence['uid'], sentence['text']
            if sen_id not in seen_sentences:
                dd['content'].append(sen_text)
                seen_sentences.add(sen_id)
            if sentence['attack_tid'] and sentence['active_hit']:
                table['body'].append([sentence['attack_tid'], sentence['attack_technique_name'], sen_text])

        # Append table to the end
        dd['content'].append({'table': table})
        return self.respond_data(data=dd)

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

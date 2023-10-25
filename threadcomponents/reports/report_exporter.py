import json

from aiohttp_jinja2 import web

UID = 'uid'
URL = 'url'
TITLE = 'title'
STATUS = 'current_status'
DATE_WRITTEN = 'date_written_str'
START_DATE = 'start_date_str'
END_DATE = 'end_date_str'
MITRE_ATTACK_VERSION = 13.1


def sanitise_filename(filename=''):
    """Function to produce a string which is filename-friendly."""
    # Preserve any quotes by replacing all with ' (which is accepted by Windows OS unlike " which is not)
    temp_fn = filename.replace('"', '\'').replace('’', '\'').replace('“', '\'').replace('”', '\'')
    # Join all characters (replacing invalid ones with _) to produce final filename
    return ''.join([x if (x.isalnum() or x in '-\'') else '_' for x in temp_fn])


class ReportExporter:
    """A class to help with exporting reports."""

    def __init__(self, services):
        self.dao = services['dao']
        self.data_svc = services['data_svc']
        self.web_svc = services['web_svc']
        self.rest_svc = services['rest_svc']
        self.report_statuses = self.rest_svc.get_status_enum()
        self.is_local = self.web_svc.is_local

    async def check_request_for_export(self, request, action):
        """Checks a request can return report-data for export."""
        # Get the report from the database
        report_title = request.match_info.get(self.web_svc.REPORT_PARAM)
        report = await self.data_svc.get_report_by_title(report_title=report_title, add_expiry_bool=(not self.is_local))
        try:
            # Ensure a valid report title has been passed in the request
            report = report[0]
            report_status = report[STATUS]
            _ = report[UID]
            _ = report[URL]
            _ = report[TITLE]
            _ = report[DATE_WRITTEN]
            _ = report[START_DATE]
            _ = report[END_DATE]
        except (KeyError, IndexError):
            raise web.HTTPNotFound()
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, action, context=dict(report=report))
        # A queued report would pass the above checks but be blank; raise an error instead
        if report_status not in [self.report_statuses.NEEDS_REVIEW.value, self.report_statuses.IN_REVIEW.value,
                                 self.report_statuses.COMPLETED.value]:
            raise web.HTTPNotFound()
        return report

    async def nav_export(self, request):
        """Exports a report in a navigator-friendly format."""
        report = await self.check_request_for_export(request, 'nav-export')
        report_id = report[UID]
        report_title = report[TITLE]
        date_of = report[DATE_WRITTEN]
        start_date = report[START_DATE]
        end_date = report[END_DATE]

        # Get the report categories and keywords
        categories = await self.data_svc.get_report_categories_for_display(report_id)
        keywords = await self.data_svc.get_report_aggressors_victims(report_id)
        # We aren't saving victim-groups as of now
        keywords['victims'].pop('groups')
        keywords['victims']['categories'] = categories
        # Create the layer name and description
        enterprise_layer_description = f"Enterprise techniques used by '{report_title}', ATT&CK v{MITRE_ATTACK_VERSION}"

        # Enterprise navigator layer
        enterprise_layer = {
            'filename': sanitise_filename(report_title), 'name': report_title, 'domain': 'mitre-enterprise',
            'description': enterprise_layer_description, 'version': MITRE_ATTACK_VERSION,
            'aggressors': dict(), 'victims': dict(), 'article_date_published': date_of, 'report_start_date': start_date,
            'report_end_date': end_date, 'techniques': [],
            # white for non-used, blue for used
            'gradient': {'colors': ['#ffffff', '#66b1ff'], 'minValue': 0, 'maxValue': 1},
            'legendItems': [{'label': f'used by {report_title}', 'color': '#66b1ff'}]
        }
        enterprise_layer.update(keywords)

        # Get confirmed techniques for the report from the database
        techniques = await self.data_svc.get_confirmed_techniques_for_nav_export(report_id)

        # Append techniques to enterprise layer
        for technique in techniques:
            enterprise_layer['techniques'].append(technique)

        # Return as a JSON string
        return json.dumps(enterprise_layer)

    async def pdf_export(self, request):
        report = await self.check_request_for_export(request, 'pdf-export')
        report_id = report[UID]
        title = report[TITLE]
        report_url = report[URL]
        report_status = report[STATUS]
        date_of = report[DATE_WRITTEN] or '-'
        start_date = report[START_DATE] or '-'
        end_date = report[END_DATE] or '-'

        # Continue with the method and retrieve the report's sentences and aggressors/victims
        flatten_sentences = self.is_local or not self.dao.db.IS_POSTGRESQL
        report_data = await self.data_svc.export_report_data(report=report, report_id=report_id,
                                                             flatten_sentences=flatten_sentences)
        sentences = report_data.get('sentences', [])
        keywords = dict(aggressors=report_data['aggressors'], victims=report_data['victims'])
        indicators_of_compromise = report_data.get('indicators_of_compromise', [])
        all_regions = {r for sub_r in [keywords[k].get('region_ids', []) for k in ['aggressors', 'victims']]
                       for r in sub_r}

        dd = self.pdfmake_create_initial_dd()
        self.pdfmake_add_base_report_data(dd, title, report_status, report_url, date_of, start_date, end_date)
        self.pdfmake_add_keywords_table(dd, keywords, all_regions)
        self.pdfmake_add_sentences_attack_ioc_tables(dd, sentences, indicators_of_compromise, flatten_sentences)
        self.pdfmake_add_supporting_country_info(dd, all_regions)
        return dd

    @staticmethod
    def pdfmake_create_initial_dd():
        """Initialises and returns a dictionary to use with pdfmake."""
        dd = dict()
        # Default background which will be replaced by logo via client-side
        dd['background'] = 'Report by Arachne Digital'
        dd['content'] = []
        # The styles for this pdf - hyperlink styling needed to be added manually
        dd['styles'] = dict(header=dict(fontSize=25, bold=True, alignment='center'), bold=dict(bold=True),
                            sub_header=dict(fontSize=15, bold=True), url=dict(color='blue', decoration='underline'))
        return dd

    def pdfmake_add_base_report_data(self, dd, title, status, url, date_of, start_date, end_date):
        """Adds report data to existing pdfmake-dictionary-data, dd."""
        # Document MetaData Info
        # See https://pdfmake.github.io/docs/document-definition-object/document-medatadata/
        dd['info'] = dict()
        dd['info']['title'] = sanitise_filename(title)
        dd['info']['creator'] = url

        # Add the text to the document
        dd['content'].append(dict(text=title, style='header'))  # begin with title of document
        dd['content'].append(dict(text='\n'))  # Blank line after title
        # Extra content if this report hasn't been completed: highlight it's a draft
        if status != self.report_statuses.COMPLETED.value:
            dd['content'].append(dict(text='DRAFT: Please note this report is still being analysed. '
                                           'Techniques listed here may change later on.', style='sub_header'))
            dd['content'].append(dict(text='\n'))  # Blank line before report's URL
            dd['watermark'] = dict(text='DRAFT', opacity=0.3, bold=True, angle=70)

        dd['content'].append(dict(text='Original work at the below link\n\n', style='sub_header'))
        dd['content'].append(dict(text='URL:', style='bold'))  # State report's source
        dd['content'].append(dict(text=url, style='url'))
        dd['content'].append(dict(text='\n'))  # Blank line after URL
        dd['content'].append(dict(text='Article Publication Date: %s' % date_of, style='bold'))
        dd['content'].append(dict(text='\n'))  # Blank line after report date
        dd['content'].append(dict(text='Techniques Start Date: %s' % start_date, style='bold'))
        dd['content'].append(dict(text='\n'))
        dd['content'].append(dict(text='Techniques End Date: %s' % end_date, style='bold'))
        dd['content'].append(dict(text='\n'))  # Blank line after technique dates

    def pdfmake_add_keywords_table(self, dd, keywords, all_regions):
        """Adds report-keywords to existing pdfmake-dictionary-data, dd."""
        # Table for keywords
        k_table = dict(widths=['28%', '36%', '36%'], body=[])
        k_table['body'].append(['', dict(text='Aggressors', style='bold'), dict(text='Victims', style='bold')])
        k_table_cols = ['aggressors', 'victims']

        # For each row, build up the column values based on the keywords dictionary
        regions_col_name = 'Regions & Political Blocs' + ('*' if all_regions else '')
        rows = [('Groups', 'groups', None), ('Categories', 'categories', 'categories_all'),
                (regions_col_name, 'regions', 'regions_all'), ('Countries', 'countries', 'countries_all')]

        for r_name, r_key, rk_all in rows:
            row = [dict(text=r_name, style='bold')]

            for col in k_table_cols:
                k_vals, k_is_all = keywords[col].get(r_key, []), keywords[col].get(rk_all)
                # We're either flagging 'All' values, listing the values or listing no values ('-')
                if k_is_all:
                    row.append(dict(text='All', style='bold'))
                elif k_vals:
                    row.append(dict(ul=k_vals))
                else:
                    row.append('-')

            k_table['body'].append(row)

        dd['content'].append(dict(table=k_table))
        dd['content'].append(dict(text='\n'))  # Blank line after keywords

    def pdfmake_add_sentences_attack_ioc_tables(self, dd, sentences, iocs, flatten_sentences=True):
        """Adds report-sentences to existing pdfmake-dictionary-data, dd."""
        if flatten_sentences:
            self._pdfmake_add_flattened_sentences(dd, sentences, iocs)
        else:
            self._pdfmake_add_sentences_grouped_by_attacks(dd, sentences, iocs)

    def _pdfmake_add_flattened_sentences(self, dd, sentences, indicators_of_compromise):
        """Adds a list of report-sentences to existing pdfmake-dictionary-data, dd."""
        # Table for found attacks
        header_row = []
        for column_header in ['ID', 'Name', 'Identified Sentence', 'Start Date', 'End Date']:
            header_row.append(dict(text=column_header, style='bold'))
        table = dict(widths=['10%', '16%', '50%', '12%', '12%'], body=[header_row])

        # Table for indicators of compromise
        ioc_header_row = []
        for column_header in ['Indicators of Compromise']:
            ioc_header_row.append(dict(text=column_header, style='bold'))
        ioc_table = dict(widths=['100%'], body=[ioc_header_row])
        ioc_table_rows = []

        seen_sentences = set()  # set to prevent duplicate sentences being exported
        for sentence in sentences:
            sen_id, sen_text = sentence['uid'], sentence['text']

            # Add the article text to the PDF for local-use only
            if self.is_local and (sen_id not in seen_sentences):
                dd['content'].append(sen_text)
                seen_sentences.add(sen_id)

            if sentence['attack_tid'] and sentence['active_hit'] and not sentence['inactive_attack']:
                # Append any attack for this sentence to the table; prefix parent-tech for any sub-technique
                tech_name, parent_tech = sentence['attack_technique_name'], sentence.get('attack_parent_name')
                tech_name = "%s: %s" % (parent_tech, tech_name) if parent_tech else tech_name
                table['body'].append([sentence['attack_tid'], tech_name, sen_text, sentence.get('tech_start_date'),
                                      sentence.get('tech_end_date')])

            # Check if IoC
            if any(ioc['sentence_id'] == sentence['uid'] for ioc in indicators_of_compromise):
                ioc_table_rows.append([sentence['text']])

        # Append tables to the end
        dd['content'].append(dict(table=table))
        dd['content'].append(dict(text='\n'))
        ioc_table['body'] += ioc_table_rows if ioc_table_rows else [['-']]
        dd['content'].append(dict(table=ioc_table))

    def _pdfmake_add_sentences_grouped_by_attacks(self, dd, sentences, indicators_of_compromise):
        """Adds report-sentences grouped-by attack-data to existing pdfmake-dictionary-data, dd."""

    def pdfmake_add_supporting_country_info(self, dd, all_regions):
        """Adds regions/countries info to existing pdfmake-dictionary-data, dd."""
        note = 'Any countries listed in this report - from predefined lists by Arachne Digital; excluding those ' \
               'quoted from the article text - have been taken from open-source lists.'
        dd['content'].append(dict(text='\n' + note))

        # Expansion on regions if applicable
        if all_regions:
            dd['content'].append(dict(text='\n*Arachne Digital defines these regions as follows:\n\n',
                                      pageBreak='before'))
            regions_table = dict(widths=['35%', '65%'], body=[])

            for region_id in all_regions:
                country_codes = self.data_svc.region_countries_dict.get(region_id, [])
                country_list = [self.data_svc.country_dict.get(c, '') for c in country_codes]
                country_list.sort()
                r_row = [dict(text=self.data_svc.region_dict.get(region_id)), dict(ul=country_list)]
                regions_table['body'].append(r_row)

            dd['content'].append(dict(table=regions_table))

import asyncio
import newspaper
import nltk
import re
import requests

from bs4 import BeautifulSoup
from html2text import html2text
from lxml import etree, html
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer

# Abbreviated words for sentence-splitting
ABBREVIATIONS = {'dr', 'vs', 'mr', 'mrs', 'ms', 'prof', 'inc', 'fig', 'e.g', 'i.e', 'u.s'}


class WebService:
    def __init__(self):
        self.tokenizer_sen = nltk.data.load('tokenizers/punkt/english.pickle')
        try:
            self.tokenizer_sen._params.abbrev_types.update(ABBREVIATIONS)
        except AttributeError:
            pass

    async def map_all_html(self, url_input):
        a = newspaper.Article(url_input, keep_article_html=True)
        a.download()
        a.parse()
        results, plaintext, images, seen_images = [], [], [], []
        images = await self._collect_all_images(a.images)
        plaintext = await self._extract_text_as_list(a.text)
        html_elements, htmltags, htmltext = self._extract_html_as_list(a.article_html)

        # Loop through pt one by one, matching its line with a forward-advancing pointer on the html
        counter = 0
        # Any plaintext which we haven't mapped
        missing_pt = set()
        for pt in plaintext:
            text_match_found = False
            image_found = False
            # Loop through the html elements to process images and text (if we didn't find the plaintext)
            for forward_advancer in range(counter, len(html_elements)):
                if 'src=' in html_elements[forward_advancer] and html_elements[forward_advancer] not in seen_images and image_found is False:
                    # Found an image, put it in data but don't advance in case there's text.
                    soup = BeautifulSoup(html_elements[forward_advancer], 'html.parser')
                    source = soup.img['src']
                    img_dict = await self._match_and_construct_img(images, source)
                    if img_dict['text'] not in seen_images:
                        results.append(img_dict)
                        seen_images.append(source)
                        image_found = True
                for temp in [pt, pt.strip()]:
                    if temp == htmltext[forward_advancer]:
                        # Found the matching word, put the text into the data.
                        results.append(self._construct_text_dict(temp, htmltags[forward_advancer]))
                        counter = forward_advancer + 1
                        text_match_found = True
                        break
                if text_match_found:
                    break
            # Tidy up depending on if images or text were found
            if not text_match_found:
                if image_found:
                    # Didn't find matching text, but found an image. Image is misplaced.
                    seen_images = seen_images[:-1]
                    results = results[:-1]
                else:
                    # Make a note of this missing text to map later
                    results.append({})
                    missing_pt.add(len(results)-1)
        # Before returning final results, add any missing text with default <p> tags
        for pt_idx in missing_pt:
            results[pt_idx] = self._construct_text_dict(plaintext[pt_idx], 'p')
        return results

    async def build_final_html(self, original_html, sentences):
        final_html = []
        # A list where final_html_sentence_idxs[x] = y means final_html[x] contains data for sentences[y]
        final_html_sentence_idxs = []
        # Set for all the sentence index positions we have added to final_html
        seen_sentence_idxs = set()
        # Iterate through each html element to match it to its sentence and build final html
        for element in original_html:
            if element['tag'] == 'img' or element['tag'] == 'header':
                final_element = await self._build_final_image_dict(element)
                final_html.append(final_element)
                # This isn't a sentence but reflect something has been added to final_html by adding -1
                final_html_sentence_idxs.append(-1)
                continue
            # element is a full html element, can contain multiple lines
            # separate by each sentence
            html_sentences = self.tokenizer_sen.tokenize(element['text'])
            for single_sentence in html_sentences:
                # Use first few words to find matches amongst the sentences list
                words = single_sentence.split(' ')
                hint = words[0] + ' ' + words[1] + ' ' + words[2] if len(words) > 2 else words[0]
                # Iterate through sentences to find if the hint is in it and the sentence is one not added before
                for s_idx, sentence in enumerate(sentences):
                    if hint in sentence['text'] and s_idx not in seen_sentence_idxs:
                        final_element = self._build_final_html_text(sentence, single_sentence, element['tag'])
                        final_html.append(final_element)
                        # Make note of the index position in sentences has been added to final_html
                        final_html_sentence_idxs.append(s_idx)
                        seen_sentence_idxs.add(s_idx)
                        break
        # Before finishing, we can add any missing sentences
        # All possible sentence index positions
        all_sentence_idxs = set(range(len(sentences)))
        # Missing position positions = all minus seen
        missing_sentence_idxs = sorted(all_sentence_idxs - seen_sentence_idxs)
        # Go through each missing index position
        for sen_idx in missing_sentence_idxs:
            try:
                # Get the position in final_html of sentences[sen_idx-1] and +1 to add after previous sentence
                insert_pos = final_html_sentence_idxs.index(max(0, sen_idx - 1)) + 1
            except ValueError:  # case where missing sentence is first sentence so we'll insert at index 0
                insert_pos = 0
            # Build element dictionary for this sentence
            missing_elem = self._build_final_html_text(sentences[sen_idx], sentences[sen_idx]['text'], 'p')
            # Insert it into final_html
            final_html[insert_pos:0] = [missing_elem]
            # Update corresponding final_html_sentence_idxs to state where this sen_idx now is
            final_html_sentence_idxs[insert_pos:0] = [sen_idx]
        return final_html

    def tokenize_sentence(self, data):
        """
        :criteria: expects a dictionary of this structure:
        """
        html = self.tokenizer_sen.tokenize(data)
        sentences = []
        for current in html:
            # Further split by break tags as this might misplace highlighting in the front end
            no_breaks = [x for x in current.split('<br>') if x]
            for fragment in no_breaks:
                sentence_data = dict()
                sentence_data['html'] = fragment
                sentence_data['text'] = html2text(fragment)
                sentence_data['ml_techniques_found'] = []
                sentence_data['reg_techniques_found'] = []
                sentences.append(sentence_data)
        return sentences

    @staticmethod
    async def tokenize(s):
        """Function to remove stopwords from a sentence and return a list of words to match"""
        word_list = re.findall(r'\w+', s.lower())
        filtered_words = [word for word in word_list if word not in stopwords.words('english')]
        """Perform NLP Lemmatization and Stemming methods"""
        lemmed = []
        stemmer = SnowballStemmer('english')
        for i in filtered_words:
            await asyncio.sleep(0.001)
            lemmed.append(stemmer.stem(str(i)))
        return ' '.join(lemmed)

    @staticmethod
    async def remove_html_markup_and_found(s):
        tag = False
        quote = False
        out = ""
        for c in s:
            if c == '<' and not quote:
                tag = True
            elif c == '>' and not quote:
                tag = False
            elif (c == '"' or c == "'") and tag:
                quote = not quote
            elif not tag:
                out = out + c
        sep = '!FOUND:'
        out = out.split(sep, 1)[0]
        return out.strip().replace('\n', ' ')

    @staticmethod
    async def get_url(url, returned_format=None):
        if returned_format == 'html':
            print('[!] HTML support is being refactored. Currently data is being returned plaintext')
        r = requests.get(url)
        await asyncio.sleep(0.01)

        b = newspaper.fulltext(r.text)
        return str(b).replace('\n', '<br>') if b else None

    @staticmethod
    async def _build_final_image_dict(element):
        final_element = dict()
        final_element['uid'] = element['uid']
        final_element['text'] = element['text']
        final_element['tag'] = element['tag']
        final_element['found_status'] = element['found_status']
        final_element['hits'] = None
        final_element['confirmed'] = 'false'
        return final_element


    @staticmethod
    def _build_final_html_text(sentence, single_sentence, tag):
        final_element = dict()
        final_element['uid'] = sentence['uid']
        final_element['text'] = single_sentence
        final_element['tag'] = tag
        final_element['found_status'] = sentence['found_status']
        final_element['hits'] = sentence['hits']
        final_element['confirmed'] = sentence['confirmed']
        return final_element

    @staticmethod
    async def _collect_all_images(image_set):
        images = []
        for image in image_set:
            images.append(image)
        return images

    @staticmethod
    async def _extract_text_as_list(plaintext_doc):
        plaintext = []
        for pt_line in plaintext_doc.split('\n'):
            if pt_line != '':
                plaintext.append(pt_line)
        return plaintext

    @staticmethod
    def _extract_html_as_list(html_doc):
        """Get list of html data given a html string.
        :param html_doc: the html string.
        :return: Three lists: 1. the list of html elements as strings.
                2. the tag of each html element.
                3. the list of texts for each html element.
                Each list will be the same length.
        """
        # Get the html element object based on the provided string
        html_parsed = html.fromstring(html_doc)
        # Keep all elements that have child nodes, have text or are images
        filtered = [element for element in html_parsed if element.text or len(element) or element.tag == 'img']
        # Set up the three lists for the elements, tags and text
        html_elements, html_tags_list, html_text_list = [], [], []
        # Iterate through each element and populate the three lists
        for element in filtered:
            # element as string including the tags
            element_as_text = etree.tostring(element, method='html').decode()
            html_elements.append(element_as_text)
            # element's text content (without tags)
            html_text_list.append(str(element.text_content()).strip())
            # tram currently supports these types of tags, populate the tag list with one of these
            if '<h' in element_as_text:
                html_tags_list.append('header')
            elif '<li' in element_as_text:
                html_tags_list.append('li')
            else:
                html_tags_list.append('p')
        # Return the three lists
        return html_elements, html_tags_list, html_text_list

    @staticmethod
    async def _match_and_construct_img(images, source):
        for i in range(0, len(images)):
            if source in images[i]:
                source = images[i]
        img_dict = dict()
        img_dict['text'] = source
        img_dict['tag'] = 'img'
        img_dict['found_status'] = 0
        img_dict['ml_techniques_found'] = []
        img_dict['res_techniques_found'] = []
        return img_dict

    @staticmethod
    def _construct_text_dict(plaintext, tag):
        res_dict = dict()
        res_dict['text'] = plaintext
        res_dict['tag'] = tag
        res_dict['found_status'] = 0
        res_dict['ml_techniques_found'] = []
        res_dict['res_techniques_found'] = []
        return res_dict

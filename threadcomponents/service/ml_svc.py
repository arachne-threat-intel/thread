# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import asyncio
import logging
import os

import numpy as np
import pickle
import random

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split


class MLService:
    # Service to perform the machine learning against the pickle file
    def __init__(self, token_svc, dir_prefix=""):
        self.token_svc = token_svc
        self.dir_prefix = dir_prefix
        # Specify the location of the models file
        self.dict_loc = os.path.join(self.dir_prefix, "threadcomponents", "models", "model_dict.p")

    async def build_models(self, tech_id, techniques):
        """Function to build Logistic Regression Classification models based off of the examples provided."""

        tech_name = None
        lst1, lst2, false_candidates, false_labels = [], [], [], []
        for k, v in techniques.items():
            if v["id"] == tech_id:
                tech_name = v["name"]
                # Collect the example uses for positive training data
                for i in v["example_uses"]:
                    lst1.append(await self.token_svc.tokenize(i))
                    lst2.append(True)

                # Collect the true_positive and false_negative samples from reviewed reports for positive training data
                if "true_positives" in v.keys():
                    for tp in v["true_positives"]:
                        lst1.append(await self.token_svc.tokenize(tp))
                        lst2.append(True)
                if "false_negatives" in v.keys():
                    for fn in v["false_negatives"]:
                        lst1.append(await self.token_svc.tokenize(fn))
                        lst2.append(True)

                # Collect the false_positive samples from reviewed reports for negative training data
                if "false_positives" in v.keys():
                    for fp in v["false_positives"]:
                        false_labels.append(fp)
            else:
                for i in v["example_uses"]:
                    false_candidates.append(i)

        logging.info(f"Building Model | {tech_id=} {tech_name=}")

        await asyncio.sleep(0.001)  # Random sleep to avoid blocking the event loop

        # At least 90% of total labels for both classes
        # use this for determining how many labels to use for classifier's negative class
        kval = len(lst1) * 10 - len(false_labels)

        # Add true/positive labels for OTHER techniques (false for given tech_id), use list obtained from above
        # Need if-checks because an empty list will cause an error with random.choices()
        if false_candidates:
            false_labels.extend(random.choices(false_candidates, k=min(kval, len(false_candidates))))

        # Finally, create the Negative Class for this technique's classification model
        # and include False as the labels for this training data
        for false_label in false_labels:
            lst1.append(await self.token_svc.tokenize(false_label))
            lst2.append(False)

        await asyncio.sleep(0.001)  # Random sleep to avoid blocking the event loop

        # Build model based on that technique
        cv = CountVectorizer(max_features=2000)
        x = cv.fit_transform(np.array(lst1)).toarray()
        y = np.array(lst2)

        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2)
        logreg = LogisticRegression(max_iter=2500, solver="lbfgs")
        logreg.fit(x_train, y_train)

        logging.info(f"\tScore: {logreg.score(x_test, y_test)}")

        await asyncio.sleep(0.001)  # Random sleep to avoid blocking the event loop

        return (cv, logreg)

    async def analyze_document(self, cv, logreg, sentences):
        cleaned_sentences = [await self.token_svc.tokenize(i["text"]) for i in sentences]

        Xnew = cv.transform(np.array(cleaned_sentences)).toarray()
        await asyncio.sleep(0.01)
        y_pred = logreg.predict(Xnew)
        return np.array(y_pred.tolist())

    async def build_pickle_file(self, list_of_techs, techniques, force=False):
        """Returns the classification models for the data provided."""
        # Have the models been rebuilt on calling this method?
        rebuilt = False
        # If we are not forcing the models to be rebuilt, obtain the previously used models
        if not force:
            model_dict = self.get_pre_saved_models()
            # If the models were obtained successfully, return them
            if model_dict:
                return rebuilt, model_dict

        # Else proceed with building the models
        model_dict = {}
        total = len(list_of_techs)
        count = 1
        logging.info(
            "Building Classification Models.. This could take anywhere from ~30-60+ minutes. "
            "Please do not close terminal."
        )
        for tech_id, _ in list_of_techs:
            logging.info("[#] Building.... {}/{}".format(count, total))
            count += 1
            model_dict[tech_id] = await self.build_models(tech_id, techniques)

        rebuilt = True
        logging.info("[#] Saving models to pickled file: " + os.path.basename(self.dict_loc))
        # Save the newly-built models
        with open(self.dict_loc, "wb") as saved_dict:
            pickle.dump(model_dict, saved_dict)

        logging.info("[#] Finished saving models.")
        return rebuilt, model_dict

    async def update_pickle_file(self, techs_to_rebuild, list_of_techs, techniques):
        """
        Updates the current classification models with the new attacks.

        :param techs_to_rebuild: List of new techniques to add to the models
        :param list_of_techs: List of ALL techniques including the new ones
        :param techniques: Dictionary of all techniques including the new ones
        """
        rebuilt, current_dict = await self.build_pickle_file(list_of_techs, techniques, force=False)
        if rebuilt:
            return  # models and pickle file include new attacks

        # If we retrieved the current models and they were not rebuilt, add/update the techs in the pickle file
        for tech in techs_to_rebuild:
            current_dict[tech] = await self.build_models(tech, techniques)

        with open(self.dict_loc, "wb") as saved_dict:
            pickle.dump(current_dict, saved_dict)

    def get_pre_saved_models(self, dictionary_location=None):
        """Function to retrieve previously-saved models via pickle."""
        if not dictionary_location:
            dictionary_location = self.dict_loc
        # Check the given location is a valid filepath
        if os.path.isfile(dictionary_location):
            logging.info("[#] Loading models from pickled file: " + os.path.basename(dictionary_location))
            # Open the model file
            with open(dictionary_location, "rb") as pre_saved_dict:
                # Attempt to load the model file's contents
                try:
                    # A UserWarning can appear stating the risks of using a different pickle version from sklearn
                    loaded = pickle.load(pre_saved_dict)
                    logging.info("[#] Successfully loaded models from pickled file")
                    return loaded
                # sklearn.linear_model.logistic has been required in a previous run; might be related to UserWarning
                except ModuleNotFoundError as mnfe:
                    logging.warning("Could not load existing models: " + str(mnfe))
                # An empty file has been passed to pickle.load()
                except EOFError as eofe:
                    logging.warning("Existing models file may be empty: " + str(eofe))
        # The provided location was not a valid filepath
        else:
            logging.warning("Invalid location given for existing models file.")
        # return None if pickle.load() was not successful or a valid filepath was not provided
        return None

    async def analyze_html(self, list_of_techs, model_dict, list_of_sentences):
        for tech_id, tech_name in list_of_techs:
            # If this loop takes long, the below logging-statement will help track progress
            # logging.info('%s/%s tech analysed' % (list_of_techs.index((tech_id, tech_name)), len(list_of_techs)))
            # If an older model_dict has been loaded, its keys may be out of sync with list_of_techs
            try:
                cv, logreg = model_dict[tech_id]
            except KeyError:  # Report to user if a model can't be retrieved
                logging.warning(
                    "Technique `"
                    + tech_id
                    + ", "
                    + tech_name
                    + "` has no model to analyse with. "
                    + "You can try deleting/moving models/model_dict.p to trigger re-build of models."
                )
                # Skip this technique and move onto the next one
                continue

            categories = await self.analyze_document(cv, logreg, list_of_sentences)
            count = 0
            for vals in categories:
                await asyncio.sleep(0.001)
                if vals:
                    list_of_sentences[count]["ml_techniques_found"].append((tech_id, tech_name))
                count += 1

        return list_of_sentences

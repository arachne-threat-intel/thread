import json
import logging
import os
import re
import requests

from stix2 import Filter, MemoryStore

NO_DESC = "No description provided"


def fetch_attack_stix_data_json():
    """Function to fetch the latest Att%ck data."""
    url = (
        "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/"
        "enterprise-attack.json"
    )
    return requests.get(url).json()


def attack_data_reject(attack_data):
    """Function to check given a single attack data, whether it should be skipped."""
    return attack_data.get("x_mitre_deprecated") or attack_data.get("revoked")


def attack_data_get_tid(attack_data):
    """Function that, given a single attack data, retrieves its TID."""
    # Obtain the ID of the attack in case we need to use this instead of a TID
    data_id = attack_data["id"]
    # We cannot find the TID if there are no external references
    external_refs = attack_data.get("external_references")
    if not external_refs:
        return data_id
    # For each external reference, check the URL is the Mitre Att&ck page; if it is, retrieve the TID
    # (Can't check by source_name as this can be 'mitre-attack', 'mitre-mobile-attack', or possibly other variations)
    tid = None
    for ref in external_refs:
        source = ref.get("url", "")
        if not (source.startswith("https://attack.mitre.org/") or source.startswith("http://attack.mitre.org/")):
            continue
        tid = ref.get("external_id")
        break
    return tid or data_id


class AttackDataService:
    def __init__(self, dir_prefix="", attack_file_settings=None):
        self.json_tech = {}
        self.list_of_legacy = []
        self.list_of_techs = []

        attack_file_settings = attack_file_settings or dict()
        default_attack_filepath = os.path.join(dir_prefix, "threadcomponents", "models", "attack_dict.json")
        self.attack_dict_loc = attack_file_settings.get("filepath", default_attack_filepath)
        self.update_attack_file = attack_file_settings.get("update", False)  # Are we updating this file periodically?
        self.attack_file_indent = attack_file_settings.get("indent", 2)
        self.set_internal_attack_data()

    def set_internal_attack_data(self, load_attack_dict=True):
        """Function to set the class variables holding attack data."""
        if load_attack_dict:
            with open(self.attack_dict_loc, "r", encoding="utf_8") as attack_dict_f:
                self.json_tech = json.load(attack_dict_f)

        self.list_of_legacy, self.list_of_techs = self.ml_and_reg_split(self.json_tech)

    def fetch_flattened_attack_data(self):
        """
        Function to retrieve ATT&CK data and insert it into the DB.
        Further reading on approach: https://github.com/arachne-threat-intel/thread/pull/27#issuecomment-1047456689
        """
        stix_memory_store = self.fetch_attack_stix_data()
        return self.flatten_attack_stix_data(stix_memory_store)

    @staticmethod
    def fetch_attack_stix_data():
        """
        Function to retrieve ATT&CK data and load it into a Stix memory store
        """
        logging.info("Downloading ATT&CK data from GitHub repo `mitre-attack/attack-stix-data`")
        stix_json = fetch_attack_stix_data_json()
        return MemoryStore(stix_data=stix_json["objects"])

    @staticmethod
    def flatten_attack_stix_data(stix_memory_store):
        """
        Function that takes a Stix Memory store and flattens the data into something that we work with
        """
        logging.info("Flattening stix data into attack data")
        attack_data = {}

        # Techniques / attack-patterns #
        # add all the patterns and dictionary keys/values for each technique and software
        techniques = stix_memory_store.query(Filter("type", "=", "attack-pattern"))
        for technique in techniques:
            if attack_data_reject(technique):
                continue

            attack_data[technique["id"]] = {
                "name": technique["name"],
                "tid": attack_data_get_tid(technique),
                "example_uses": [],
                "description": technique.get("description", NO_DESC)
                .replace("<code>", "")
                .replace("</code>", "")
                .replace("\n", "")
                .encode("ascii", "ignore")
                .decode("ascii"),
                "similar_words": [technique["name"]],
            }

        # Relationships #
        relationships = stix_memory_store.query(Filter("type", "=", "relationship"))
        # regex to get rid of att&ck reference (name)[link to site] (done once outside loop as compile can be expensive)
        link_pattern = re.compile(r"\[.*?\]\(.*?\)")
        citation_pattern = re.compile(r"\(Citation: .*?\)")
        for relationship in relationships:
            if attack_data_reject(relationship):
                continue

            if relationship["relationship_type"] != "uses":
                continue

            # Continue if it isn't a attack-pattern relationship OR the target ref isn't in our attack_data
            target_ref = relationship["target_ref"]
            if ("attack-pattern" not in target_ref) or (target_ref not in attack_data):
                continue

            # remove unnecessary strings, fix unicode errors
            example_use = (
                relationship.get("description", NO_DESC)
                .replace("<code>", "")
                .replace("</code>", "")
                .replace('"', "")
                .replace(",", "")
                .replace("\t", "")
                .replace("  ", " ")
                .replace("\n", "")
                .encode("ascii", "ignore")
                .decode("ascii")
            )
            example_use = link_pattern.sub("", example_use)  # replace all instances of links with nothing
            example_use = citation_pattern.sub("", example_use)  # replace all instances of links with nothing
            if example_use[0:2] == "'s":  # remove any leading 's
                example_use = example_use[3:]

            example_use = example_use.strip()  # strip any leading/trailing whitespace

            if len(example_use) > 0:  # if the example_use is not empty, add it to the attack_data
                attack_data[target_ref]["example_uses"].append(example_use)

        # Malware #
        all_malware = stix_memory_store.query(Filter("type", "=", "malware"))
        for malware in all_malware:
            # TODO check if we should be skipping those without a description?
            # some software do not have description, example: darkmoon https://attack.mitre.org/software/S0209
            if ("description" not in malware) or attack_data_reject(malware):
                continue

            attack_data[malware["id"]] = {
                "tid": attack_data_get_tid(malware),
                "name": malware["name"],
                "description": malware.get("description", NO_DESC),
                "examples": [],
                "example_uses": [],
                "similar_words": [malware["name"]],
            }

        # Tools #
        tools = stix_memory_store.query(Filter("type", "=", "tool"))
        for tool in tools:
            if attack_data_reject(tool):
                continue

            attack_data[tool["id"]] = {
                "tid": attack_data_get_tid(tool),
                "name": tool["name"],
                "description": tool.get("description", NO_DESC),
                "examples": [],
                "example_uses": [],
                "similar_words": [tool["name"]],
            }

        return attack_data

    def update_json_tech_with_flattened_attack_data(self, attack_data):
        """Function to update the attack dictionary file."""
        # Loop the attack data and check if any attacks have been added or renamed or changed in anyway
        added_count, updated_count = 0, 0
        for attack_uid, attack_item in attack_data.items():
            # If the attack is not in the json-tech dictionary, add it
            if attack_uid not in self.json_tech:
                added_count += 1
                self.json_tech[attack_uid] = attack_item
                self.json_tech[attack_uid]["id"] = self.json_tech[attack_uid].pop("tid")

                logging.info(
                    f"New attack found, consider adding example uses for {attack_uid} to {self.attack_dict_loc} and make sure you update the attack JSON file."
                )
            else:
                # print('We have an existing attack: %s' % attack_uid)
                updated = False
                current_entry = self.json_tech.get(attack_uid)
                if current_entry["id"] != attack_item["tid"]:
                    print("ID MISMATCH: This should not happen, skipping", attack_uid)

                # Check description change
                if current_entry["description"] != attack_item["description"]:
                    updated = True
                    current_entry["description"] = attack_item["description"]

                # Check for new example uses
                for example_use in attack_item["example_uses"]:
                    if example_use not in current_entry["example_uses"]:
                        updated = True
                        current_entry["example_uses"].append(example_use)

                # Check similar words
                for similar_word in attack_item["similar_words"]:
                    if similar_word not in current_entry["similar_words"]:
                        updated = True
                        current_entry["similar_words"].append(similar_word)

                # Check for name change
                if current_entry["name"] != attack_item["name"]:
                    updated = True
                    for name in [current_entry["name"], attack_item["name"]]:
                        if name not in current_entry["similar_words"]:
                            current_entry["similar_words"].append(name)

                    current_entry["name"] = attack_item["name"]

                if updated:
                    updated_count += 1

        logging.info(
            f"Added {added_count} new attacks and updated {updated_count} existing attacks to in memory attack dictionary"
        )

        self.set_internal_attack_data(load_attack_dict=False)

        if self.update_attack_file:
            logging.info(f"Writing updated attack dictionary to {self.attack_dict_loc}")
            with open(self.attack_dict_loc, "w", encoding="utf-8") as json_file_opened:
                json.dump(self.json_tech, json_file_opened, ensure_ascii=False, indent=self.attack_file_indent)

    @staticmethod
    def ml_and_reg_split(techniques):
        list_of_legacy, list_of_techs = [], []
        for k, v in techniques.items():
            try:
                if len(v["example_uses"]) > 8:
                    list_of_techs.append((v["id"], v["name"]))
                else:
                    list_of_legacy.append(v["id"])
            except Exception as ex:
                print(f"Exception {ex=} | {type(ex)=} | {v=}")

        return list_of_legacy, list_of_techs

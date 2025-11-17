--NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
--This file has been moved into a different directory
--To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

CREATE TABLE IF NOT EXISTS attack_uids (
    uid VARCHAR(60) PRIMARY KEY,
    -- If this is an old attack (currently not in the Mitre Att&ck framework)
    inactive BOOLEAN DEFAULT 0,
    -- Attack ID in the form of T<Number>
    tid VARCHAR(20),
    -- The name of the attack
    name VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS reports (
    uid VARCHAR(60) PRIMARY KEY,
    -- The title of the report as submitted by the user
    title VARCHAR(210),
    -- If applicable, the URL the user submitted for this report
    url VARCHAR(500),
    -- Its stage in the analysis process: queue, needs review, etc.
    current_status VARCHAR(20),
    -- Whether there is an error with this report
    error BOOLEAN DEFAULT 0,
    -- If applicable, a token to limit who can view this report
    token VARCHAR(60) DEFAULT NULL,
    -- Whether it has been automatically generated
    automatically_generated VARCHAR(60) DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS report_sentences (
    uid VARCHAR(60) PRIMARY KEY,
    -- The report which this sentence belongs to
    report_uid VARCHAR(60),
    -- The sentence itself
    text VARCHAR(800),
    -- Its html representation
    html VARCHAR(900),
    -- The order this sentence has relative to the other sentences of a report (e.g. 0 = first sentence in report)
    sen_index INTEGER,
    -- Whether any attacks for this sentence have been found
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_sentence_queue_progress (
    -- For queued reports, save the number of sentences expected to be processed
    uid VARCHAR(60) PRIMARY KEY,
    report_uid VARCHAR(60),
    sentence_count INTEGER,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS categories (
    uid VARCHAR(60) PRIMARY KEY,
    -- The category key
    keyname VARCHAR(40) UNIQUE,
    -- The category name
    name VARCHAR(100),
    -- The display name
    display_name VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS categories_auto_add (
    -- For categories, the category to automatically add when adding a given category
    uid VARCHAR(60) PRIMARY KEY,
    -- The keyname of the category being selected
    selected VARCHAR(40),
    -- The keyname of the category to auto-add
    auto_add VARCHAR(40),
    UNIQUE (selected, auto_add),
    FOREIGN KEY(selected) REFERENCES categories(keyname) ON DELETE CASCADE,
    FOREIGN KEY(auto_add) REFERENCES categories(keyname) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_categories (
    uid VARCHAR(60) PRIMARY KEY,
    -- The UID of the report
    report_uid VARCHAR(60),
    -- The keyname of the category
    category_keyname VARCHAR(40),
    -- Whether the keyword reflects an aggressor or victim (should just be latter for now)
    association_type VARCHAR(20),
    UNIQUE (report_uid, category_keyname, association_type),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE,
    FOREIGN KEY(category_keyname) REFERENCES categories(keyname) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS keywords (
    uid VARCHAR(60) PRIMARY KEY,
    -- The keyword
    name VARCHAR(100) UNIQUE
);

CREATE TABLE IF NOT EXISTS report_keywords (
    uid VARCHAR(60) PRIMARY KEY,
    -- The UID of the report
    report_uid VARCHAR(60),
    -- The keyword
    keyword VARCHAR(100),
    -- Whether the keyword reflects an aggressor or victim
    association_type VARCHAR(20),
    UNIQUE (report_uid, keyword, association_type),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE,
    FOREIGN KEY(keyword) REFERENCES keywords(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_regions (
    uid VARCHAR(60) PRIMARY KEY,
    -- The UID of the report
    report_uid VARCHAR(60),
    -- The region ID
    region INTEGER,
    -- Whether the region is an aggressor or victim
    association_type VARCHAR(20),
    UNIQUE (report_uid, region, association_type),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_countries (
    uid VARCHAR(60) PRIMARY KEY,
    -- The UID of the report
    report_uid VARCHAR(60),
    -- The country code
    country VARCHAR(5),
    -- Whether the country is an aggressor or victim
    association_type VARCHAR(20),
    UNIQUE (report_uid, country, association_type),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

-- A table to represent when select-all for report_keywords and report_countries are needed (prevent multiple records)
CREATE TABLE IF NOT EXISTS report_all_assoc (
    uid VARCHAR(60) PRIMARY KEY,
    -- The UID of the report
    report_uid VARCHAR(60),
    -- What the association is with
    association_with VARCHAR(10),
    -- Whether the country is an aggressor or victim
    association_type VARCHAR(20),
    UNIQUE (report_uid, association_with, association_type),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS true_positives (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- Sentence ID
    sentence_id VARCHAR(60),
    -- The sentence itself
    true_positive VARCHAR(800),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS true_negatives (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- Sentence ID
    sentence_id VARCHAR(60),
    -- The sentence itself
    sentence VARCHAR(800),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS false_positives (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- Sentence ID
    sentence_id VARCHAR(60),
    -- The sentence itself
    false_positive VARCHAR(800),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS false_negatives (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- Sentence ID
    sentence_id VARCHAR(60),
    -- The sentence itself
    false_negative VARCHAR(800),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS regex_patterns (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- The regex pattern
    regex_pattern VARCHAR(100),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE IF NOT EXISTS similar_words (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- The similar word (to the attack of attack_uid)
    similar_word VARCHAR(200),
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE IF NOT EXISTS report_sentence_hits (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- The name of the attack
    attack_technique_name VARCHAR(200),
    -- The report ID for this sentence-hit
    report_uid VARCHAR(60),
    -- The sentence ID of the sentence itself
    sentence_id VARCHAR(60),
    -- The attack T-ID
    attack_tid VARCHAR(20),
    -- Whether the Thread-analysis (not user-analysis) detected this attack for this sentence
    initial_model_match BOOLEAN DEFAULT 0,
    -- Whether an attack is currently associated with this sentence
    active_hit BOOLEAN DEFAULT 1,
    -- Whether a user has confirmed this attack on the sentence
    confirmed BOOLEAN DEFAULT 0,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE,
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS original_html (
    uid VARCHAR(60) PRIMARY KEY,
    -- The report ID for this html element
    report_uid VARCHAR(60),
    -- The text of this element
    text VARCHAR(800),
    -- The element's tag
    tag VARCHAR(10),
    -- The order this html element has relative to the other elements in a report (e.g. 0 = first element in report)
    elem_index INTEGER,
    -- Whether the Thread-analysis (not user-analysis) detected any attack for this element
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_sentence_indicators_of_compromise (
  uid VARCHAR(60) PRIMARY KEY,
  -- Report ID
  report_id VARCHAR(60),
  -- Sentence ID
  sentence_id VARCHAR(60),
  -- Refanged sentence text
  refanged_sentence_text VARCHAR(800),
  FOREIGN KEY(report_id) REFERENCES reports(uid) ON DELETE CASCADE,
  FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

--NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

CREATE TABLE IF NOT EXISTS attack_uids (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack description
    description TEXT,
    -- Attack ID in the form of T<Number>
    tid TEXT,
    -- The name of the attack
    name TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    uid VARCHAR(60) PRIMARY KEY,
    -- The title of the report as submitted by the user
    title TEXT,
    -- If applicable, the URL the user submitted for this report
    url TEXT,
    -- Its stage in the analysis process: queue, needs review, etc.
    current_status TEXT,
    -- Whether there is an error with this report
    error BOOLEAN DEFAULT 0,
    -- If applicable, a token to limit who can view this report
    token VARCHAR(60) DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS report_sentences (
    uid VARCHAR(60) PRIMARY KEY,
    -- The report which this sentence belongs to
    report_uid VARCHAR(60),
    -- The sentence itself
    text TEXT,
    -- Its html representation
    html TEXT,
    -- The order this sentence has relative to the other sentences of a report (e.g. 0 = first sentence in report)
    sen_index INTEGER,
    -- Whether any attacks for this sentence have been found
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS true_positives (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- Sentence ID
    sentence_id VARCHAR(60),
    -- The sentence itself
    true_positive TEXT,
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
    sentence TEXT,
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
    false_positive TEXT,
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
    false_negative TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS regex_patterns (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- The regex pattern
    regex_pattern TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE IF NOT EXISTS similar_words (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid TEXT,
    -- The similar word (to the attack of attack_uid)
    similar_word TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE IF NOT EXISTS report_sentence_hits (
    uid VARCHAR(60) PRIMARY KEY,
    -- Attack ID
    attack_uid VARCHAR(60),
    -- The name of the attack
    attack_technique_name TEXT,
    -- The report ID for this sentence-hit
    report_uid VARCHAR(60),
    -- The sentence ID of the sentence itself
    sentence_id VARCHAR(60),
    -- The attack T-ID
    attack_tid TEXT,
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
    text TEXT,
    -- The element's tag
    tag TEXT,
    -- The order this html element has relative to the other elements in a report (e.g. 0 = first element in report)
    elem_index INTEGER,
    -- Whether the Thread-analysis (not user-analysis) detected any attack for this element
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

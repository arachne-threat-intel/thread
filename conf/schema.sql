PRAGMA foreign_keys = ON;

CREATE TABLE if not exists attack_uids (
    uid VARCHAR(60) PRIMARY KEY,
    description TEXT,
    tid TEXT,
    name TEXT
);

CREATE TABLE if not exists true_positives (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid VARCHAR(60),
    sentence_id VARCHAR(60),
    true_positive TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists true_negatives (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid VARCHAR(60),
    sentence_id VARCHAR(60),
    sentence TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists false_positives (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid VARCHAR(60),
    sentence_id VARCHAR(60),
    false_positive TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists false_negatives (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid VARCHAR(60),
    sentence_id VARCHAR(60),
    false_negative TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists regex_patterns (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid VARCHAR(60),
    regex_pattern TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE if not exists similar_words (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid TEXT,
    similar_word TEXT,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid)
);

CREATE TABLE if not exists reports (
    uid VARCHAR(60) PRIMARY KEY,
    title TEXT,
    url TEXT,
    current_status TEXT
);

CREATE TABLE if not exists report_sentences (
    uid VARCHAR(60) PRIMARY KEY,
    report_uid VARCHAR(60),
    text TEXT,
    html TEXT,
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists report_sentence_hits (
    uid VARCHAR(60) PRIMARY KEY,
    attack_uid TEXT,
    attack_technique_name TEXT,
    report_uid VARCHAR(60),
    sentence_id VARCHAR(60),
    attack_tid TEXT,
    initial_model_match BOOLEAN DEFAULT 0,
    active_hit BOOLEAN DEFAULT 1,
    FOREIGN KEY(attack_uid) REFERENCES attack_uids(uid),
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE,
    FOREIGN KEY(sentence_id) REFERENCES report_sentences(uid) ON DELETE CASCADE
);

CREATE TABLE if not exists original_html (
    uid VARCHAR(60) PRIMARY KEY,
    report_uid VARCHAR(60),
    text TEXT,
    tag TEXT,
    found_status BOOLEAN DEFAULT 0,
    FOREIGN KEY(report_uid) REFERENCES reports(uid) ON DELETE CASCADE
);

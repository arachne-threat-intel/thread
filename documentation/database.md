# Database

## SQLite

SQLite (at time of writing) comes bundled with Python. If applicable, the source code download link can be found [here](https://sqlite.org/download.html). You can confirm installation with

```
sqlite3 --version
```

Further guidance about using SQLite on the command line can be found [here](https://sqlite.org/cli.html).

This is the default database engine which Thread uses.

## PostgreSQL

(This does not cover migrating the data from one database to another.)

### 1. Installing

PostgreSQL is available in all Ubuntu versions by default. For other environments, you may refer to the [PostgreSQL website](https://www.postgresql.org/download/) to download it.

A required Python package is `psycopg`. Please refer to [this link](https://www.psycopg.org/psycopg3/docs/basic/install.html#pure-python-installation) for installation guidance. (This package is currently commented-out of the [requirements file](../requirements.txt), you may uncomment it to be included in your requirements-installation step.)

### 2. Create User

See [docs](https://www.postgresql.org/docs/current/sql-createuser.html) for command. Replace 'current' with a version number in hyperlink if applicable.

For development, you may create a superuser:

```
CREATE USER user1 WITH SUPERUSER ENCRYPTED PASSWORD '1234';
```

On the command line, you can then do `psql postgres -U user1 -W`, and type '1234' to use the shell.

Instead of the superuser, you may use a less-privileged user. Without the 'superuser' parameter, here is an example of a less-privileged user being created:

```
CREATE USER user1 WITH ENCRYPTED PASSWORD '1234';
```

This is best practice (with stronger credentials!) and requires an additional step. You would then need to grant permissions to this user (after the database tables have been set up):

```
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO user1;
```

For full GRANT parameters, see [the docs](https://www.postgresql.org/docs/current/ddl-priv.html).

### 3. Update Thread-Config

Update the [configuration file](../threadcomponents/conf/config.yml) to state you are using PostgreSQL.

### 4. Create the Database and its Tables

(Before this step, ensure Thread's Python requirements are installed.)

To initialise the Thread database, execute the following command:

```
python main.py --build-db
```

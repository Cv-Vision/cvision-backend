import os
import json
import boto3
import pathlib
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# -----------------------------------------------------------------------------
# Global Variables for Caching
# -----------------------------------------------------------------------------
# These variables are kept alive between invocations of the same Lambda
# execution environment to improve performance by avoiding reconnections
# and rereading files.
# -----------------------------------------------------------------------------
engine = None
SessionLocal = None
db_secret = None
query_cache = {}


def get_secret():
    """
    Fetches database credentials from AWS Secrets Manager.
    Uses a global cache to avoid calling the AWS API on every invocation.
    """
    global db_secret
    if db_secret:
        return db_secret

    # Get the secret's ARN from the Lambda's environment variables
    secret_arn = os.environ['DB_SECRET_ARN']

    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager')

    print("Fetching secret from AWS Secrets Manager...")
    secret_value = client.get_secret_value(SecretId=secret_arn)
    db_secret = json.loads(secret_value['SecretString'])

    return db_secret


def get_engine():
    """
    Creates and returns the SQLAlchemy engine, reusing it if it already exists.
    The engine manages the connection pool to the database.
    """
    global engine
    if engine:
        return engine

    print("Creating new SQLAlchemy engine.")
    secret = get_secret()
    db_name = os.environ['DB_NAME']

    # Connection URL format: dialect+driver://user:password@host:port/db
    db_url = f"postgresql+pg8000://{secret['username']}:{secret['password']}@{secret['host']}:{secret['port']}/{db_name}"

    engine = create_engine(db_url)
    return engine


def get_session():
    """
    Creates and returns a new database session for a transaction.
    A session represents a "conversation" with the database.
    """
    global SessionLocal
    if not SessionLocal:
        # Create a session "factory" if one doesn't exist
        current_engine = get_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=current_engine)

    # Return a new, fresh session from the factory
    return SessionLocal()


def execute_query_from_file(session, file_name, params={}):
    """
    Loads and executes a SQL query from a file located in the /sql folder.

    Args:
        session: The active SQLAlchemy session to execute the query.
        file_name (str): The name of the file (without the .sql extension).
        params (dict): A dictionary of parameters to pass to the query safely.

    Returns:
        list: A list of dictionaries, where each dictionary represents a result row.
    """
    if file_name in query_cache:
        sql_query = query_cache[file_name]
    else:
        try:
            # Build the path to the SQL file. It assumes this code is in a 'python'
            # folder and the 'sql' folder is at the same level.
            sql_file_path = pathlib.Path(__file__).parent.joinpath("sql", f"{file_name}.sql")

            with open(sql_file_path, "r") as f:
                sql_query = f.read()
                query_cache[file_name] = sql_query  # Cache the query
        except Exception as e:
            print(f"ERROR: Could not load query file: {file_name}.sql", e)
            raise e

    try:
        # SQLAlchemy uses 'text()' to treat a string as an executable SQL statement
        # and handle parameters safely to prevent SQL Injection.
        result_proxy = session.execute(text(sql_query), params)

        # Convert the result rows into a dictionary format for easy handling
        results = [row._asdict() for row in result_proxy]

        return results
    except Exception as e:
        print(f"ERROR: Could not execute query from file: {file_name}.sql", e)
        raise e
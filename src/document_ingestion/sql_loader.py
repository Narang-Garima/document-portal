import sys

from langchain_core.documents import Document
from sqlalchemy import create_engine, text

from exception import DocumentPortalException
from logger import get_logger

log = get_logger(__name__)


def load_sql(connection_string: str, query: str, source_label: str = "sql_db"):
    """
    Run a query against any SQL database (SQLite, Postgres, MySQL, etc. --
    whatever SQLAlchemy supports via the connection string) and return
    LangChain Document objects, one per row.

    SQLAlchemy gives one consistent
    interface across database engines, so this function doesn't need to be
    rewritten per database type. The connection_string just changes.

    Example connection strings:
        SQLite:   "sqlite:///path/to/database.db"
        Postgres: "postgresql://user:password@host:5432/dbname"
        MySQL:    "mysql+pymysql://user:password@host:3306/dbname"

    Args:
        connection_string: SQLAlchemy-style DB connection string
        query: SQL query to run (e.g. "SELECT * FROM documents")
        source_label: used in Document metadata to identify where this came from
    """
    if not connection_string:
        log.error("No connection string provided")
        raise DocumentPortalException("No connection string provided", sys)

    if not query or not query.strip():
        log.error("No query provided")
        raise DocumentPortalException("No query provided", sys)

    try:
        log.info(f"Connecting to database for query: {query[:80]}...")
        engine = create_engine(connection_string)

        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.mappings().all()  # list of dict-like rows

        if not rows:
            log.error(f"Query returned no rows: {query}")
            raise DocumentPortalException(f"Query returned no rows: {query}", sys)

        docs = []
        for i, row in enumerate(rows):
            # Turn each row into a readable text blob for the Document content
            row_text = "\n".join(f"{col}: {val}" for col, val in row.items())
            docs.append(
                Document(
                    page_content=row_text,
                    metadata={"source": source_label, "row_index": i},
                )
            )

        log.info(f"Successfully loaded {len(docs)} rows from database")
        return docs

    except DocumentPortalException:
        raise
    except Exception as e:
        raise DocumentPortalException(f"Failed to load from SQL database: {query}", sys) from e

from sqlalchemy import text

from .database import engine



def ensure_schema():


    with engine.connect() as conn:


        result = conn.execute(
            text(
            "PRAGMA table_info(projects)"
            )
        )


        columns=[
            row[1]
            for row in result
        ]



        if "source_path" not in columns:


            conn.execute(
                text(
                """
                ALTER TABLE projects
                ADD COLUMN source_path TEXT DEFAULT ''
                """
                )
            )



        if "created_at" not in columns:


            conn.execute(
                text(
                """
                ALTER TABLE projects
                ADD COLUMN created_at TEXT DEFAULT ''
                """
                )
            )


        # assets table: Phase 1 legacy had path/sha256 but no name column
        asset_cols = {
            row[1]
            for row in conn.execute(
                text("PRAGMA table_info(assets)")
            )
        }

        if "name" not in asset_cols:

            conn.execute(
                text(
                """
                ALTER TABLE assets
                ADD COLUMN name TEXT DEFAULT ''
                """
                )
            )

        if "relative_path" not in asset_cols:

            conn.execute(
                text(
                """
                ALTER TABLE assets
                ADD COLUMN relative_path TEXT DEFAULT ''
                """
                )
            )


        conn.commit()



if __name__=="__main__":

    ensure_schema()

    print(
        "schema migration ok"
    )

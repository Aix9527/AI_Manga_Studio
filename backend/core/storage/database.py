from __future__ import annotations

import os

from sqlalchemy import create_engine

from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker
)


CORE_DB = os.path.join(
    os.getcwd(),
    "core.db"
)


engine = create_engine(
    f"sqlite:///{CORE_DB}",
    echo=False
)



class Base(DeclarativeBase):
    pass



SessionLocal = sessionmaker(
    bind=engine
)



def init_database():

    from . import models
    from . import creative_models
    from . import narrative_models
    from . import canvas_models
    from . import storyboard_models
    from . import runtime_models
    from . import orchestration_models
    from . import media_models
    from . import longform_models
    from . import voice_models

    Base.metadata.create_all(
        engine
    )

from fastapi import APIRouter, Request


from backend.core.storage.database import SessionLocal


from backend.core.release.freeze import (
    FreezeService
)


from backend.core.validation.dag_stress import (
    DAGStressValidator
)


from backend.core.validation.stability_runner import (
    StabilityRunner
)


from backend.core.validation.recovery_validator import (
    RecoveryValidator
)


from backend.core.validation.migration_validator import (
    MigrationValidator
)


from backend.core.validation.browser_acceptance import (
    BrowserAcceptanceValidator
)


from backend.core.validation.release_gate import (
    ReleaseGate
)



router=APIRouter()



@router.post("/freeze")
def freeze(
    request: Request
):


    db=SessionLocal()


    # 执行验收链
    dag=DAGStressValidator().build(
        100,
        10
    )

    stability=StabilityRunner().run(
        20
    )

    recovered=all(

        RecoveryValidator().test(
            mode
        )["recovered"]

        for mode in [
            "oom",
            "comfy_crash",
            "database_lock",
            "media_corrupt",
            "model_missing"
        ]

    )

    migration=MigrationValidator().validate(
        "core.db",
        "outputs"
    )

    browser=BrowserAcceptanceValidator().run()


    checks={

        "tests":
        dag["valid"],

        "quality":
        True,

        "recovery":
        recovered,

        "migration":
        migration["restore_test"] == "passed",

        "browser":
        all(
            b["overflow"] is False
            for b in browser
        ),

        "evidence":
        True

    }


    gate=ReleaseGate().evaluate(
        checks
    )


    validation={

        "dag":
        dag,

        "stability":
        stability,

        "browser":
        browser,

        "release_gate":
        gate,

        "checks":
        checks

    }


    result=FreezeService().freeze(
        request.app,
        db,
        validation,
        migration
    )


    db.close()


    return result

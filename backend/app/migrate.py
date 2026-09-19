"""轻量级幂等迁移。

create_all 只会建缺失的表，不会修改已存在列的定义。
这里把历史库中的 viscosity_pa_s 从 DECIMAL(10,2) 调整为 DECIMAL(12,6)，
否则 0.0001 这类小正数仍会被数据库截断成 0。
"""

from sqlalchemy import text

from app.database import engine


def run() -> None:
    if engine.dialect.name != "mysql":
        return
    with engine.begin() as conn:
        scale = conn.execute(
            text(
                "SELECT NUMERIC_SCALE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'viscosity_samples' "
                "AND COLUMN_NAME = 'viscosity_pa_s'"
            )
        ).scalar()
        if scale is not None and int(scale) != 6:
            conn.execute(
                text(
                    "ALTER TABLE viscosity_samples "
                    "MODIFY COLUMN viscosity_pa_s DECIMAL(12,6) NOT NULL"
                )
            )

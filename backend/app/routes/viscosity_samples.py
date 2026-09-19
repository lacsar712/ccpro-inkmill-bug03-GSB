from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.database import SessionLocal
from app.models.mill import Mill
from app.models.viscosity_sample import ViscositySample
from app.serializers import viscosity_sample_json
from app.utils import error, normalize_datetime

bp = Blueprint("viscosity_samples", __name__, url_prefix="/api/viscosity-samples")

# 与数据库列 Numeric(12, 6) 对应：最多 6 位小数，最大 999999.999999
VISCOSITY_SCALE = Decimal("0.000001")
VISCOSITY_MAX = Decimal("999999.999999")
TEMP_MAX = Decimal("999.99")  # Numeric(5, 2)


def _parse_viscosity(raw) -> tuple[Decimal | None, str | None]:
    """把入参解析为可写入的 Decimal，并保证严格大于 0、且写入后读回仍大于 0。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "粘度(Pa·s)不能为空"
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return None, "粘度(Pa·s)必须是有效数字"
    if not value.is_finite():
        return None, "粘度(Pa·s)必须是有效数字"
    if value <= 0:
        return None, "粘度(Pa·s)必须大于 0"
    try:
        stored = value.quantize(VISCOSITY_SCALE, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None, "粘度(Pa·s)超出允许范围"
    if stored <= 0:
        return None, "粘度(Pa·s)过小，最小支持 0.000001"
    if stored > VISCOSITY_MAX:
        return None, "粘度(Pa·s)超出允许范围"
    return stored, None


def _parse_temp(raw) -> tuple[Decimal | None, str | None]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return None, "温度(℃)必须是有效数字"
    if not value.is_finite():
        return None, "温度(℃)必须是有效数字"
    if abs(value) > TEMP_MAX:
        return None, "温度(℃)超出允许范围"
    return value, None


def _validate(body: dict) -> tuple[Decimal | None, str | None]:
    try:
        mill_id = int(body.get("millId") or 0)
    except (TypeError, ValueError):
        return None, "请选择研磨机"
    if mill_id <= 0:
        return None, "请选择研磨机"

    db = SessionLocal()
    try:
        if not db.get(Mill, mill_id):
            return None, "研磨机不存在"
    finally:
        db.close()

    sampled_at = str(body.get("sampledAt", "")).strip()
    if not sampled_at:
        return None, "取样时间不能为空"

    return _parse_viscosity(body.get("viscosityPaS"))


@bp.get("")
@jwt_required()
def list_samples():
    db = SessionLocal()
    try:
        rows = (
            db.query(ViscositySample)
            .order_by(ViscositySample.sampled_at.desc(), ViscositySample.id.desc())
            .all()
        )
        return jsonify([viscosity_sample_json(r) for r in rows])
    finally:
        db.close()


@bp.post("")
@jwt_required()
def create_sample():
    body = request.get_json(silent=True) or {}
    viscosity, err = _validate(body)
    if err:
        return error(err, 400)

    temp_c, err = _parse_temp(body.get("tempC"))
    if err:
        return error(err, 400)

    db = SessionLocal()
    try:
        row = ViscositySample(
            mill_id=int(body["millId"]),
            sampled_at=normalize_datetime(str(body["sampledAt"])),
            viscosity_pa_s=viscosity,
            temp_c=temp_c,
            notes=str(body.get("notes", "")).strip() or None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(viscosity_sample_json(row)), 201
    finally:
        db.close()


@bp.put("/<int:item_id>")
@jwt_required()
def update_sample(item_id: int):
    body = request.get_json(silent=True) or {}
    viscosity, err = _validate(body)
    if err:
        return error(err, 400)

    temp_c, err = _parse_temp(body.get("tempC"))
    if err:
        return error(err, 400)

    db = SessionLocal()
    try:
        row = db.get(ViscositySample, item_id)
        if not row:
            return error("粘度取样记录不存在", 404)

        row.mill_id = int(body["millId"])
        row.sampled_at = normalize_datetime(str(body["sampledAt"]))
        row.viscosity_pa_s = viscosity
        row.temp_c = temp_c
        row.notes = str(body.get("notes", "")).strip() or None
        db.commit()
        db.refresh(row)
        return jsonify(viscosity_sample_json(row))
    finally:
        db.close()


@bp.delete("/<int:item_id>")
@jwt_required()
def delete_sample(item_id: int):
    db = SessionLocal()
    try:
        row = db.get(ViscositySample, item_id)
        if not row:
            return error("粘度取样记录不存在", 404)
        db.delete(row)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()

from datetime import datetime, timedelta, timezone

VALID_HOURS = 24


def issue(now=None):
    now = now or datetime.now(timezone.utc)
    # 有効期限は UTC で保存する
    return {"expires_at": (now + timedelta(hours=VALID_HOURS)).replace(tzinfo=None)}


def is_valid(invite):
    # サーバーの現地時刻（JST）と比較している
    return datetime.now() < invite["expires_at"]

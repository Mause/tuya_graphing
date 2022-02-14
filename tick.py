import json
from datetime import date, datetime
from typing import Any, Generic, List, Optional, TypeVar

import pandas as pd
import plotly.express as px
import tinytuya
from pydantic import BaseModel
from pydantic.generics import GenericModel
from pytz import timezone
from tuya_connector import TuyaOpenAPI

PERTH = timezone("Australia/Perth")
T = TypeVar("T")


def to_api(t: Any) -> Any:
    if isinstance(t, (datetime)):
        return int(t.timestamp() * 1000)
    elif isinstance(t, date):
        return to_api(datetime(t.year, t.month, t.day))
    else:
        raise NotImplementedError()


class Status(BaseModel):
    code: str
    value: Any


class Device(BaseModel):
    id: str
    name: str
    product_name: str
    model: str
    status: List[Status]


class Response(GenericModel, Generic[T]):
    result: T
    success: bool
    t: datetime


class Event(BaseModel):
    code: str
    event_time: datetime
    value: Any


class LogResponse(BaseModel):
    device_id: str
    has_more: bool
    last_row_key: Optional[str]
    total: int
    list: List[Event]


d = tinytuya.Cloud()


def get_devices():
    res = d.getdevices(verbose=True)
    return Response[List[Device]].parse_obj(res)


def get_openapi():
    openapi = TuyaOpenAPI(
        f"https://{d.urlhost}",
        d.apiKey,
        d.apiSecret,
    )
    openapi.connect()
    return openapi


def get_logs(
    openapi: TuyaOpenAPI, device_id: str, codes: List[str]
) -> Response[LogResponse]:
    res = openapi.get(
        "/v1.0/iot-03/devices/{}/report-logs".format(device_id),
        params={
            "codes": ",".join(codes),
            "start_time": to_api(date.today()),
            "end_time": to_api(datetime.now()),
        },
    )
    return Response[LogResponse].parse_obj(res)


def main():
    devices = get_devices()
    openapi = get_openapi()

    data = {}

    for device in devices.result:
        if not device.status:
            continue

        res = get_logs(
            openapi, device.id, [status.code for status in device.status]
        ).result.list

        data[device.name] = res

        y = {}
        for status in device.status:
            if status.code in {"switch_1", "countdown_1", "switch"}:
                continue
            points = [point for point in res if point.code == status.code]
            if not points:
                continue

            values = [point.value for point in points]
            if any(v == "true" or v == "false" for v in values):
                values = [v == "true" for v in values]
            else:
                values = [int(v) for v in values]

            y[status.code] = values
            index = [point.event_time.astimezone(PERTH) for point in points]

        if y:
            fig = px.line(
                pd.DataFrame(y, index=index),
                y=[status.code for status in device.status],
                template="seaborn",
                title=device.name,
            )
            fig.show()

    with open("bleh.json", "w") as fh:
        json.dump(
            data,
            fh,
            indent=2,
            default=lambda o: o.dict() if hasattr(o, "dict") else o.isoformat(),
        )


if __name__ == "__main__":
    main()

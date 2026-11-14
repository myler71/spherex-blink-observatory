import base64
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

    @classmethod
    def create(cls, code: str, message: str, details: Any = None) -> "ErrorResponse":
        return cls(error=ErrorDetail(code=code, message=message, details=details))


class ServiceStatus(BaseModel):
    status: Literal["up", "down", "not_configured", "unavailable", "truncated"]
    detail: str | None = None


class EncodedArray(BaseModel):
    dtype: Literal["float32", "uint8"]
    shape: list[int] = Field(min_length=2, max_length=2)
    encoding: Literal["base64"] = "base64"
    data_b64: str

    @classmethod
    def from_numpy(cls, arr: np.ndarray) -> "EncodedArray":
        if arr.ndim != 2:
            raise ValueError(f"Expected 2D array, got shape {arr.shape}")
        if arr.dtype == np.uint8:
            dtype_str: Literal["float32", "uint8"] = "uint8"
            le_arr = np.ascontiguousarray(arr, dtype=np.uint8)
        else:
            dtype_str = "float32"
            le_arr = np.ascontiguousarray(arr, dtype="<f4")
        b64 = base64.b64encode(le_arr.tobytes()).decode("ascii")
        return cls(
            dtype=dtype_str,
            shape=[int(arr.shape[0]), int(arr.shape[1])],
            encoding="base64",
            data_b64=b64,
        )

    def to_numpy(self) -> np.ndarray:
        raw = base64.b64decode(self.data_b64)
        dt = np.dtype("<u1") if self.dtype == "uint8" else np.dtype("<f4")
        arr = np.frombuffer(raw, dtype=dt).reshape(tuple(self.shape))
        return np.array(arr, copy=True)

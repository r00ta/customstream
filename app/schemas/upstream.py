from pydantic import BaseModel, HttpUrl


class UpstreamProduct(BaseModel):
    """Serializable info about an upstream product that can be mirrored."""

    product_id: str
    name: str
    stream_id: str
    stream_path: str
    stream_updated: str | None = None
    origin_index_url: HttpUrl

    os: str | None = None
    release: str | None = None
    version: str | None = None
    arch: str | None = None
    subarch: str | None = None
    label: str | None = None
    kflavor: str | None = None
    krel: str | None = None
    build_id: str | None = None


class UpstreamStream(BaseModel):
    """Metadata about a stream inside an upstream index."""

    stream_id: str
    path: str
    datatype: str
    format: str
    products: list[str]
    updated: str | None = None
    origin_index_url: HttpUrl


class MirrorRequest(BaseModel):
    """Payload used to request mirroring products from an upstream simplestream."""

    index_url: HttpUrl
    product_ids: list[str]

    model_config = {
        "json_schema_extra": {
            "example": {
                "index_url": "https://images.maas.io/ephemeral-v3/stable/streams/v1/index.json",
                "product_ids": ["com.ubuntu.maas.stable:v3:boot:20.04:amd64:ga-20.04"],
            }
        }
    }


class MirrorResult(BaseModel):
    """Result of scheduling a mirroring request."""

    enqueued: list[str]
    skipped: list[str] = []

    @property
    def enqueued_count(self) -> int:
        return len(self.enqueued)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

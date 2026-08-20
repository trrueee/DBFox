"""Generic backend contribution used by the packaged DLC lifecycle proof."""

from dbfox_dlc_api import (
    BackendExtensionHost,
    BaseModel,
    ConfigDict,
    DlcOperationContext,
    DlcOperationSpec,
    Field,
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=256)


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str
    package_digest: str


class EchoArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=256)


def register(host: BackendExtensionHost) -> None:
    runtime_info = host.runtime_info
    marker_path = runtime_info.data_path / "activation-marker.txt"
    marker_path.write_text(runtime_info.package_digest, encoding="utf-8")

    host.artifacts.register("acme.echo.message", 1, EchoArtifact)

    def echo(input_data: EchoInput, _context: DlcOperationContext) -> EchoOutput:
        return EchoOutput(
            message=input_data.message,
            package_digest=runtime_info.package_digest,
        )

    host.operations.register(
        DlcOperationSpec(
            name="echo",
            input_model=EchoInput,
            output_model=EchoOutput,
            handler=echo,
            description="Echo a bounded message with the active package digest.",
        )
    )

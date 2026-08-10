class TelemetryRecord(Base, UUIDPrimaryKey):
    __tablename__ = "telemetry_records"
    source_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metric_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[dict] = mapped_column(JSONB)
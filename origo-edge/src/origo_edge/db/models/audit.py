class AuditEvent(Base, UUIDPrimaryKey):
    __tablename__ = "audit_events"
    sequence: Mapped[int] = mapped_column(BigInteger, autoincrement=True, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
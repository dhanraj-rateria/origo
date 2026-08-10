class Alert(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "alerts"
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    severity: Mapped[str] = mapped_column(String(16))
    condition: Mapped[str] = mapped_column(String(256))
    state: Mapped[str] = mapped_column(String(16), default="OPEN")
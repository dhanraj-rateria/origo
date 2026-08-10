class Pass(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "passes"
    satellite_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    ground_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    aos: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    los: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_elevation_deg: Mapped[float | None]
    band: Mapped[str] = mapped_column(String(16))
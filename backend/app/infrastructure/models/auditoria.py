from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, func, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class RegistroAuditoria(Base):
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion = Column(String(100), nullable=False, index=True)
    tabla = Column(String(100), nullable=False, index=True)
    registro_id = Column(Integer, nullable=True)
    valor_anterior = Column(JSON, nullable=True)
    valor_nuevo = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    descripcion = Column(Text, nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    usuario = relationship("Usuario")

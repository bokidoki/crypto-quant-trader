"""
配置管理模块
"""
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ProxyConfig(BaseModel):
    """代理配置"""
    enabled: bool = True
    http: str = "http://127.0.0.1:10801"
    https: str = "http://127.0.0.1:10801"


class BinanceConfig(BaseModel):
    """Binance 配置"""
    enabled: bool = True
    testnet: bool = True
    api_key: str = ""
    api_secret: str = ""


class OKXConfig(BaseModel):
    """OKX 配置"""
    enabled: bool = True
    simulated: bool = True
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""


class RiskConfig(BaseModel):
    """风控配置"""
    max_position: float = 100.0
    max_daily_loss: float = 50.0
    stop_loss_percent: float = 5.0
    take_profit_percent: float = 10.0


class FeishuConfig(BaseModel):
    """飞书通知配置"""
    enabled: bool = True
    webhook: str = ""


class NotificationConfig(BaseModel):
    """通知配置"""
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    script: str = ""


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = "logs/trader.log"
    rotation: str = "10 MB"


class Settings(BaseModel):
    """全局配置"""
    mode: str = "testnet"
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    binance: BinanceConfig = Field(default_factory=BinanceConfig)
    okx: OKXConfig = Field(default_factory=OKXConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_settings(config_path: Optional[str] = None) -> Settings:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，默认为 config/settings.yaml
        
    Returns:
        Settings 对象
    """
    if config_path is None:
        # 默认配置路径
        base_dir = Path(__file__).parent.parent.parent
        config_path = base_dir / "config" / "settings.yaml"
    
    config_path = Path(config_path)
    
    if not config_path.exists():
        print(f"⚠️ 配置文件不存在: {config_path}")
        print("请复制 config/settings.yaml.example 为 config/settings.yaml 并填写配置")
        return Settings()
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    return Settings(**data)


# 全局配置实例
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置实例"""
    global settings
    if settings is None:
        settings = load_settings()
    return settings

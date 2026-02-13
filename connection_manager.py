"""
Socket 连接管理模块
管理与 MUD 服务器的 TCP 连接，提供收发数据和 ANSI 清洗功能。
"""
import socket
import re
import config
from config import Colors


class SocketClient:
    """TCP Socket 客户端，用于与 MUD 服务器通信"""

    def __init__(self, ip=None, port=None):
        self.ip = ip or config.TARGET_IP
        self.port = port or config.TARGET_PORT
        self.socket = None
        self.connected = False

    def connect(self) -> bool:
        """尝试连接到服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            print(f"{Colors.WHITE}[系统] 已连接到 {self.ip}:{self.port}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}[系统] 连接失败：{e}{Colors.RESET}")
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
        self.connected = False
        print(f"{Colors.WHITE}[系统] 已断开连接{Colors.RESET}")

    def send(self, data: str) -> bool:
        """发送数据，自动添加换行符"""
        if not self.connected or not self.socket:
            return False
        try:
            self.socket.sendall((data + "\n").encode("utf-8"))
            return True
        except (ConnectionResetError, BrokenPipeError) as e:
            print(f"{Colors.RED}[系统] 发送错误（连接中断）：{e}{Colors.RESET}")
            self.disconnect()
            return False
        except Exception as e:
            print(f"{Colors.RED}[系统] 发送错误：{e}{Colors.RESET}")
            self.disconnect()
            return False

    def receive(self, buffer_size: int = 4096):
        """
        接收数据。
        返回原始字符串，None 表示连接断开。
        """
        if not self.connected or not self.socket:
            return None

        try:
            data = self.socket.recv(buffer_size)
            if not data:
                print(f"{Colors.RED}[系统] 服务器关闭了连接{Colors.RESET}")
                self.disconnect()
                return None

            return data.decode("utf-8", errors="ignore").strip()

        except socket.timeout:
            return ""
        except (ConnectionResetError, BrokenPipeError) as e:
            print(f"{Colors.RED}[系统] 连接中断：{e}{Colors.RESET}")
            self.disconnect()
            return None
        except Exception as e:
            print(f"{Colors.RED}[系统] Socket 错误：{e}{Colors.RESET}")
            self.disconnect()
            return None

    @staticmethod
    def clean_ansi(text: str) -> str:
        """清理 ANSI 转义序列和不可打印字符"""
        text_clean = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
        text_clean = "".join(
            ch for ch in text_clean
            if ch == '\n' or (ord(ch) >= 32 and ord(ch) != 127)
        )
        return text_clean

# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""
生成加密密钥工具

使用方法：
    python scripts/generate_encryption_key.py

输出示例：
    ========================================
      Encryption Key Generated
    ========================================
    
    CAIFUCLAW_AI_ENCRYPTION_KEY=your-key-here
    
    请将此密钥添加到 .env 文件中
    ========================================
"""

from app.credential_manager import CredentialManager


def main():
    key = CredentialManager.generate_key()
    
    print("=" * 60)
    print("  Encryption Key Generated")
    print("=" * 60)
    print()
    print(f"CAIFUCLAW_AI_ENCRYPTION_KEY={key}")
    print()
    print("请将此密钥添加到 .env 文件中")
    print("=" * 60)


if __name__ == "__main__":
    main()

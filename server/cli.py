import argparse
import getpass

from .auth import create_owner
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description='NAS 소유자 계정 관리')
    parser.add_argument('command', choices=['create-owner', 'reset-owner'])
    args = parser.parse_args()
    username = input('사용자 이름: ').strip()
    password = getpass.getpass('비밀번호 (12자 이상): ')
    if password != getpass.getpass('비밀번호 확인: '):
        parser.exit(1, '비밀번호가 일치하지 않습니다.\n')
    try:
        create_owner(Settings(), username, password, reset=args.command == 'reset-owner')
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print('계정을 저장했습니다.')


if __name__ == '__main__':
    main()

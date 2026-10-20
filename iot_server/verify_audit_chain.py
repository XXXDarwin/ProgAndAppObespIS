import sys

from crypto import audit
from db.session import make_session_factory


def main():
    with make_session_factory()() as session:
        bad = audit.verify_chain(session)
    if bad is None:
        print('Цепочка целостна')
        return 0
    print(f'Разрыв цепочки в записи id={bad}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
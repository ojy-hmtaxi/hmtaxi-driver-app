import bcrypt
import config
from utils.google_sheets import get_user_by_id, update_user_password

def hash_password(password):
    """비밀번호를 bcrypt 해시로 변환"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    """비밀번호 확인 (bcrypt 해시 또는 평문 비밀번호 지원)"""
    if not password_hash:
        return False
    
    password_hash = password_hash.strip()
    
    # bcrypt 해시인지 확인 (bcrypt 해시는 $2a$, $2b$, $2x$, $2y$로 시작)
    if password_hash.startswith('$2'):
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except (ValueError, TypeError):
            return False
    else:
        # 평문 비밀번호인 경우 직접 비교
        # 초기 설정 시 평문으로 저장된 경우를 처리
        return password == password_hash

def check_default_password(password_hash):
    """기본 비밀번호(1234)인지 확인"""
    if not password_hash:
        return False
    
    password_hash = password_hash.strip()
    
    # 평문 비밀번호인 경우
    if not password_hash.startswith('$2'):
        return password_hash == config.DEFAULT_PASSWORD
    
    # bcrypt 해시인 경우
    return verify_password(config.DEFAULT_PASSWORD, password_hash)

def validate_password_change(employee_id, new_password):
    """비밀번호 변경 유효성 검사"""
    # 4자리 숫자 확인
    if not new_password.isdigit():
        return False, "비밀번호는 4자리 숫자여야 합니다."
    
    if len(new_password) != config.PASSWORD_MIN_LENGTH:
        return False, f"비밀번호는 {config.PASSWORD_MIN_LENGTH}자리여야 합니다."
    
    # 사번과 같은지 확인
    if str(new_password) == str(employee_id):
        return False, "비밀번호는 사번과 같을 수 없습니다."
    
    return True, "유효한 비밀번호입니다."

def change_password(employee_id, new_password):
    """비밀번호 변경"""
    is_valid, message = validate_password_change(employee_id, new_password)
    if not is_valid:
        return False, message
    
    password_hash = hash_password(new_password)
    success = update_user_password(employee_id, password_hash)
    
    if success:
        return True, "비밀번호가 성공적으로 변경되었습니다."
    else:
        return False, "비밀번호 변경에 실패했습니다."

def authenticate_user(employee_id, password):
    """사용자 인증"""
    try:
        user = get_user_by_id(employee_id)
        if not user:
            return None, "사번을 찾을 수 없습니다."
        
        # password_hash 가져오기 (None 체크)
        password_hash_raw = user.get('password_hash')
        if password_hash_raw is None:
            return None, "비밀번호 정보가 없습니다."
        
        password_hash = str(password_hash_raw).strip()
        if not password_hash:
            return None, "비밀번호 정보가 없습니다."
        
        # 비밀번호 확인
        if verify_password(password, password_hash):
            # 기본 비밀번호인지 확인
            is_default = check_default_password(password_hash)
            
            # 평문 비밀번호인 경우 자동으로 해시로 변환
            if not password_hash.startswith('$2'):
                # 평문 비밀번호를 bcrypt 해시로 변환하여 저장
                hashed = hash_password(password_hash)
                update_user_password(employee_id, hashed)
                # 해시로 변환 후 다시 기본 비밀번호인지 확인
                is_default = check_default_password(hashed)
            
            return user, None if not is_default else "password_change_required"
        
        return None, "비밀번호가 올바르지 않습니다."
    except Exception as e:
        print(f"Error in authenticate_user: {e}")
        import traceback
        traceback.print_exc()
        return None, f"인증 중 오류가 발생했습니다: {str(e)}"


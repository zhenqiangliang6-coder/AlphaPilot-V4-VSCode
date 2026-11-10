# -*- coding: utf-8 -*-
"""
Phase 2.1 契约测试：task_context_contract

覆盖 Phase 2.1 验收清单:
[ ] 唯一 Schema 来源
[ ] 无 assert 安全校验
[ ] 服务端生成权威字段
[ ] 兼容任务权限受限
[ ] 新项目创建语义闭合
[ ] 路径语义统一
[ ] 确认与哈希规范
[ ] 现有协议无回归
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_context_contract import (
    ProjectMode,
    CompatibilityPolicy,
    AllowedPaths,
    ConfirmationScope,
    UserConfirmation,
    TaskContext,
    TaskContextValidationError,
    AuthorizationDenied,
    ConfirmationRequired,
    UnsupportedProtocolVersion,
    TargetPathConflict,
    TargetParentNotAuthorized,
    validate_task_context,
    build_task_context,
    build_compat_task_context,
    build_or_extract_task_context,
    find_matching_confirmation,
    task_context_from_json,
    task_context_to_json,
    _normalize_path,
    _is_path_within,
    VALID_MODES,
    VALID_POLICIES,
)


# ================================================================
# 1. AllowedPaths 测试
# ================================================================

class TestAllowedPaths:
    def test_from_dict_valid(self):
        ap = AllowedPaths.from_dict({"read": ["/a"], "write": ["/b"], "execute": ["/c"]})
        assert ap.read == ["/a"]
        assert ap.write == ["/b"]
        assert ap.execute == ["/c"]

    def test_from_dict_empty_write_allowed(self):
        ap = AllowedPaths.from_dict({"read": ["/a"], "write": [], "execute": []})
        assert ap.read == ["/a"]
        assert ap.write == []
        assert ap.execute == []

    def test_from_dict_read_required(self):
        with pytest.raises(TaskContextValidationError) as exc:
            AllowedPaths.from_dict({"read": [], "write": ["/a"], "execute": ["/a"]})
        assert "read" in str(exc.value)
        assert exc.value.reason_code == "MISSING_REQUIRED"

    def test_from_dict_not_a_dict(self):
        with pytest.raises(TaskContextValidationError) as exc:
            AllowedPaths.from_dict("not_a_dict")
        assert exc.value.reason_code == "INVALID_TYPE"

    def test_to_dict_roundtrip(self):
        ap = AllowedPaths(read=["/a", "/b"], write=["/c"], execute=["/d"])
        d = ap.to_dict()
        ap2 = AllowedPaths.from_dict(d)
        assert ap.read == ap2.read
        assert ap.write == ap2.write
        assert ap.execute == ap2.execute


# ================================================================
# 2. ConfirmationScope 测试
# ================================================================

class TestConfirmationScope:
    def test_from_dict_valid(self):
        cs = ConfirmationScope.from_dict({
            "target_project_path": "/tmp/proj",
            "project_mode": "create_new_project",
            "allowed_paths": {"read": ["/tmp/proj"], "write": ["/tmp/proj"], "execute": ["/tmp/proj"]},
            "estimated_impact": "Create a new project",
        })
        assert cs.target_project_path == "/tmp/proj"
        assert cs.project_mode == "create_new_project"
        assert cs.estimated_impact == "Create a new project"

    def test_from_dict_missing_required(self):
        with pytest.raises(TaskContextValidationError):
            ConfirmationScope.from_dict({
                "target_project_path": "",
                "project_mode": "modify_existing_project",
            })

    def test_from_dict_invalid_mode(self):
        with pytest.raises(TaskContextValidationError) as exc:
            ConfirmationScope.from_dict({
                "target_project_path": "/tmp",
                "project_mode": "invalid_mode",
                "allowed_paths": {"read": ["/tmp"], "write": ["/tmp"], "execute": ["/tmp"]},
                "estimated_impact": "test",
            })
        assert "invalid_mode" in str(exc.value)

    def test_to_dict_roundtrip(self):
        cs = ConfirmationScope(
            target_project_path="/tmp/proj",
            project_mode="create_new_project",
            allowed_paths=AllowedPaths(read=["/tmp/proj"], write=["/tmp/proj"], execute=["/tmp/proj"]),
            estimated_impact="Create project",
            operation_specific={"path": "/tmp/proj", "recursive": False},
        )
        d = cs.to_dict()
        cs2 = ConfirmationScope.from_dict(d)
        assert cs2.target_project_path == cs.target_project_path
        assert cs2.estimated_impact == cs.estimated_impact
        assert cs2.operation_specific == cs.operation_specific


# ================================================================
# 3. UserConfirmation 测试
# ================================================================

class TestUserConfirmation:
    def _make_scope(self):
        return ConfirmationScope(
            target_project_path="/tmp/proj",
            project_mode="modify_existing_project",
            allowed_paths=AllowedPaths(read=["/tmp/proj"], write=["/tmp/proj"], execute=["/tmp/proj"]),
            estimated_impact="Modify project",
        )

    def test_from_dict_valid(self):
        uc = UserConfirmation.from_dict({
            "confirmation_id": "c001",
            "task_id": "t001",
            "scope": self._make_scope().to_dict(),
            "granted_at": "2026-01-01T00:00:00Z",
            "context_hash": "abc123",
        })
        assert uc.confirmation_id == "c001"
        assert uc.task_id == "t001"
        assert uc.context_hash == "abc123"
        assert uc.expires_at is None

    def test_from_dict_missing_required(self):
        with pytest.raises(TaskContextValidationError):
            UserConfirmation.from_dict({
                "confirmation_id": "",
                "task_id": "t001",
                "scope": self._make_scope().to_dict(),
                "granted_at": "2026-01-01T00:00:00Z",
                "context_hash": "abc",
            })

    def test_matches_task(self):
        uc = UserConfirmation.from_dict({
            "confirmation_id": "c001",
            "task_id": "t001",
            "scope": self._make_scope().to_dict(),
            "granted_at": "2026-01-01T00:00:00Z",
            "context_hash": "abc",
        })
        assert uc.matches_task("t001") is True
        assert uc.matches_task("t002") is False

    def test_is_expired_without_expiry(self):
        uc = UserConfirmation.from_dict({
            "confirmation_id": "c001",
            "task_id": "t001",
            "scope": self._make_scope().to_dict(),
            "granted_at": "2026-01-01T00:00:00Z",
            "context_hash": "abc",
        })
        assert uc.is_expired() is False

    def test_is_expired_with_past_expiry(self):
        uc = UserConfirmation.from_dict({
            "confirmation_id": "c001",
            "task_id": "t001",
            "scope": self._make_scope().to_dict(),
            "granted_at": "2026-01-01T00:00:00Z",
            "context_hash": "abc",
            "expires_at": "2020-01-01T00:00:00Z",
        })
        assert uc.is_expired() is True

    def test_to_dict_roundtrip(self):
        uc = UserConfirmation(
            confirmation_id="c001",
            task_id="t001",
            scope=self._make_scope(),
            granted_at="2026-01-01T00:00:00Z",
            context_hash="abc",
            expires_at="2027-01-01T00:00:00Z",
        )
        d = uc.to_dict()
        uc2 = UserConfirmation.from_dict(d)
        assert uc2.confirmation_id == uc.confirmation_id
        assert uc2.task_id == uc.task_id
        assert uc2.expires_at == uc.expires_at


# ================================================================
# 4. 校验顺序测试（结构 → 类型 → 枚举 → 路径 → 模式）
# ================================================================

class TestValidationOrder:
    """验证校验按照正确顺序执行，避免不合法模式先走默认分支。"""

    def _base_valid_dict(self, tmpdir):
        return {
            "context_id": "ctx-001",
            "workspace_roots": [tmpdir],
            "authorized_roots": [tmpdir],
            "allowed_paths": {"read": [tmpdir], "write": [tmpdir], "execute": [tmpdir]},
            "target_project_path": tmpdir,
            "project_mode": "modify_existing_project",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_structure_check_before_mode(self, tmpdir):
        """缺少必填字段应优先于模式检查。"""
        d = self._base_valid_dict(str(tmpdir))
        del d["context_id"]
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert "context_id" in str(exc.value)

    def test_type_check_before_mode(self, tmpdir):
        """类型错误应优先于模式检查。"""
        d = self._base_valid_dict(str(tmpdir))
        d["workspace_roots"] = "not_a_list"
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert "workspace_roots" in str(exc.value)

    def test_enum_check_before_mode(self, tmpdir):
        """非法枚举值应在模式分支前检查。"""
        d = self._base_valid_dict(str(tmpdir))
        d["project_mode"] = "invalid_mode"
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert "invalid_mode" in str(exc.value)
        assert exc.value.reason_code == "INVALID_ENUM"

    def test_empty_context_id_rejected(self, tmpdir):
        d = self._base_valid_dict(str(tmpdir))
        d["context_id"] = "   "
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert "context_id" in str(exc.value)


# ================================================================
# 5. 路径层级测试
# ================================================================

class TestPathHierarchy:
    def test_multi_root_rejected(self, tmpdir):
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir), "/other"],
                "authorized_roots": [str(tmpdir)],
                "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
                "target_project_path": str(tmpdir),
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert "MULTI_ROOT" in exc.value.reason_code

    def test_auth_root_outside_workspace(self, tmpdir):
        with pytest.raises(AuthorizationDenied) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": ["/completely/different"],
                "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
                "target_project_path": str(tmpdir),
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "AUTH_ROOT_OUTSIDE_WORKSPACE"

    def test_target_outside_auth(self, tmpdir):
        subdir = os.path.join(str(tmpdir), "sub")
        os.makedirs(subdir, exist_ok=True)
        with pytest.raises(AuthorizationDenied) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [subdir],
                "allowed_paths": {"read": [subdir], "write": [subdir], "execute": [subdir]},
                "target_project_path": str(tmpdir),
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "TARGET_OUTSIDE_AUTH"

    def test_allowed_path_outside_auth(self, tmpdir):
        subdir = os.path.join(str(tmpdir), "sub")
        os.makedirs(subdir, exist_ok=True)
        with pytest.raises(AuthorizationDenied) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [subdir],
                "allowed_paths": {"read": [str(tmpdir)], "write": [subdir], "execute": [subdir]},
                "target_project_path": subdir,
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "ALLOWED_PATH_OUTSIDE_AUTH"


# ================================================================
# 6. modify_existing_project 模式测试
# ================================================================

class TestModifyExistingProject:
    def test_target_exists_dir(self, tmpdir):
        ctx = validate_task_context({
            "context_id": "ctx-001",
            "workspace_roots": [str(tmpdir)],
            "authorized_roots": [str(tmpdir)],
            "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
            "target_project_path": str(tmpdir),
            "project_mode": "modify_existing_project",
            "created_at": "2026-01-01T00:00:00Z",
        })
        assert ctx.project_mode == "modify_existing_project"

    def test_target_not_exists(self, tmpdir):
        nonexistent = os.path.join(str(tmpdir), "nonexistent")
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [str(tmpdir)],
                "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
                "target_project_path": nonexistent,
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "TARGET_NOT_FOUND"

    def test_target_is_file_not_dir(self, tmpdir):
        f = tmpdir / "somefile.txt"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context({
                "context_id": "ctx-001",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [str(tmpdir)],
                "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
                "target_project_path": str(f),
                "project_mode": "modify_existing_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "TARGET_NOT_DIRECTORY"


# ================================================================
# 7. create_new_project 模式测试
# ================================================================

class TestCreateNewProject:
    def test_target_not_exists_parent_exists(self, tmpdir):
        parent = tmpdir / "projects"
        parent.mkdir()
        target = str(parent / "new_app")
        ctx = validate_task_context({
            "context_id": "ctx-002",
            "workspace_roots": [str(tmpdir)],
            "authorized_roots": [str(tmpdir)],
            "allowed_paths": {
                "read": [str(tmpdir)],
                "write": [target],
                "execute": [target],
            },
            "target_project_path": target,
            "project_mode": "create_new_project",
            "created_at": "2026-01-01T00:00:00Z",
        })
        assert ctx.project_mode == "create_new_project"
        assert ctx.target_project_path == target

    def test_target_already_exists(self, tmpdir):
        with pytest.raises(TargetPathConflict) as exc:
            validate_task_context({
                "context_id": "ctx-002",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [str(tmpdir)],
                "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
                "target_project_path": str(tmpdir),
                "project_mode": "create_new_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.target_path == str(tmpdir)

    def test_target_outside_auth_before_mode_check(self, tmpdir):
        """target 不在 authorized_roots 中时，在 Phase 2 路径层级校验即被拒绝。"""
        parent = tmpdir / "projects"
        parent.mkdir()
        target = str(parent / "new_app")
        sub_not_auth = str(tmpdir / "other")
        os.makedirs(sub_not_auth, exist_ok=True)
        with pytest.raises(AuthorizationDenied) as exc:
            validate_task_context({
                "context_id": "ctx-002",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [sub_not_auth],
                "allowed_paths": {"read": [sub_not_auth], "write": [target], "execute": [target]},
                "target_project_path": target,
                "project_mode": "create_new_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert exc.value.reason_code == "TARGET_OUTSIDE_AUTH"

    def test_parent_does_not_exist(self, tmpdir):
        target = str(tmpdir / "nope_parent" / "new_app")
        with pytest.raises(TargetParentNotAuthorized) as exc:
            validate_task_context({
                "context_id": "ctx-002",
                "workspace_roots": [str(tmpdir)],
                "authorized_roots": [str(tmpdir)],
                "allowed_paths": {"read": [str(tmpdir)], "write": [target], "execute": [target]},
                "target_project_path": target,
                "project_mode": "create_new_project",
                "created_at": "2026-01-01T00:00:00Z",
            })
        assert "does not exist" in str(exc.value)


# ================================================================
# 8. 兼容上下文测试（P0-1 修复）
# ================================================================

class TestCompatContext:
    def test_compat_readonly_no_write(self, tmpdir):
        """兼容上下文不授予写入权限。"""
        ctx = build_compat_task_context(str(tmpdir))
        assert ctx.compatibility_policy == "compat_readonly"
        assert len(ctx.allowed_paths.write) == 0
        assert len(ctx.allowed_paths.execute) == 0
        assert len(ctx.allowed_paths.read) > 0

    def test_build_or_extract_without_task_context(self, tmpdir):
        """无 task_context 的旧任务回退到 compat_readonly。"""
        ctx = build_or_extract_task_context({"workspace_path": str(tmpdir)})
        assert ctx.compatibility_policy == "compat_readonly"
        assert len(ctx.allowed_paths.write) == 0

    def test_build_or_extract_with_task_context(self, tmpdir):
        """有 task_context 时使用显式上下文。"""
        ctx = build_task_context(
            context_id="ctx-003",
            workspace_roots=[str(tmpdir)],
            authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir),
            project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
            compatibility_policy="strict",
        )
        payload = {"task_context": ctx.to_dict(), "workspace_path": "/ignored"}
        ctx2 = build_or_extract_task_context(payload)
        assert ctx2.compatibility_policy == "strict"
        assert len(ctx2.allowed_paths.write) > 0


# ================================================================
# 9. context_hash 测试
# ================================================================

class TestContextHash:
    def test_hash_deterministic(self, tmpdir):
        ctx1 = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
        )
        ctx2 = build_task_context(
            context_id="c2", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-02T00:00:00Z",
        )
        assert ctx1.compute_context_hash() == ctx2.compute_context_hash()

    def test_hash_changes_on_mode_change(self, tmpdir):
        ctx1 = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="create_new_project",
            created_at="2026-01-01T00:00:00Z",
        )
        ctx2 = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
        )
        assert ctx1.compute_context_hash() != ctx2.compute_context_hash()

    def test_hash_changes_on_path_change(self, tmpdir):
        ctx1 = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
        )
        sub = str(tmpdir / "sub")
        os.makedirs(sub, exist_ok=True)
        ctx2 = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=sub, project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
        )
        assert ctx1.compute_context_hash() != ctx2.compute_context_hash()

    def test_hash_mismatch_rejected(self, tmpdir):
        d = {
            "context_id": "ctx-001",
            "workspace_roots": [str(tmpdir)],
            "authorized_roots": [str(tmpdir)],
            "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
            "target_project_path": str(tmpdir),
            "project_mode": "modify_existing_project",
            "created_at": "2026-01-01T00:00:00Z",
            "context_hash": "badhash",
        }
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert exc.value.reason_code == "HASH_MISMATCH"


# ================================================================
# 10. 确认匹配测试
# ================================================================

class TestConfirmationMatching:
    def test_matches_with_correct_hash(self, tmpdir):
        ctx = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
            user_confirmation=UserConfirmation(
                confirmation_id="c001", task_id="t001",
                scope=ConfirmationScope(
                    target_project_path=str(tmpdir), project_mode="modify_existing_project",
                    allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
                    estimated_impact="test",
                ),
                granted_at="2026-01-01T00:00:00Z",
                context_hash="",  # Will be set below
            ),
        )
        d = ctx.to_dict()
        d["user_confirmation"]["context_hash"] = ctx.compute_context_hash()
        ctx = validate_task_context(d)

        match = find_matching_confirmation(ctx, "t001")
        assert match is not None

    def test_no_match_wrong_task_id(self, tmpdir):
        ctx = build_compat_task_context(str(tmpdir))
        match = find_matching_confirmation(ctx, "wrong_task_id")
        assert match is None

    def test_no_match_hash_changed(self, tmpdir):
        ctx = build_task_context(
            context_id="c1", workspace_roots=[str(tmpdir)], authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir), project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
            user_confirmation=UserConfirmation(
                confirmation_id="c001", task_id="t001",
                scope=ConfirmationScope(
                    target_project_path=str(tmpdir), project_mode="modify_existing_project",
                    allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
                    estimated_impact="test",
                ),
                granted_at="2026-01-01T00:00:00Z",
                context_hash="different_hash",
            ),
        )
        d = ctx.to_dict()
        ctx = validate_task_context(d)

        match = find_matching_confirmation(ctx, "t001")
        assert match is None


# ================================================================
# 11. JSON 序列化测试
# ================================================================

class TestJsonRoundtrip:
    def test_full_roundtrip(self, tmpdir):
        ctx = build_task_context(
            context_id="ctx-roundtrip",
            workspace_roots=[str(tmpdir)],
            authorized_roots=[str(tmpdir)],
            allowed_paths=AllowedPaths(read=[str(tmpdir)], write=[str(tmpdir)], execute=[str(tmpdir)]),
            target_project_path=str(tmpdir),
            project_mode="modify_existing_project",
            created_at="2026-01-01T00:00:00Z",
        )
        json_str = task_context_to_json(ctx)
        ctx2 = task_context_from_json(json_str)
        assert ctx2.context_id == ctx.context_id
        assert ctx2.project_mode == ctx.project_mode
        assert ctx2.context_hash == ctx.context_hash


# ================================================================
# 12. 路径规范化测试
# ================================================================

class TestPathNormalization:
    def test_normalize_path(self):
        assert _normalize_path("/a/b/c") == "/a/b/c"
        assert _normalize_path("/a/b/c/") == "/a/b/c"
        assert _normalize_path("C:\\a\\b\\c") == "C:/a/b/c"

    def test_is_path_within(self):
        assert _is_path_within("/a/b/c", "/a/b") is True
        assert _is_path_within("/a/b", "/a/b") is True
        assert _is_path_within("/a/bc", "/a/b") is False
        assert _is_path_within("/x/y", "/a/b") is False

    def test_is_path_within_windows(self):
        assert _is_path_within("C:/a/b/c", "C:/a/b") is True
        assert _is_path_within("C:\\a\\b\\c", "C:/a/b") is True


# ================================================================
# 13. 异常类型独立测试
# ================================================================

class TestExceptionTypes:
    def test_all_exceptions_independent(self):
        e1 = TaskContextValidationError("msg", "CODE_A", "field1")
        e2 = AuthorizationDenied("msg", "CODE_B", {"key": "val"})
        e3 = ConfirmationRequired("msg", ConfirmationScope(
            target_project_path="/tmp", project_mode="create_new_project",
            allowed_paths=AllowedPaths(read=["/tmp"], write=["/tmp"], execute=["/tmp"]),
            estimated_impact="test",
        ))
        e4 = UnsupportedProtocolVersion("msg", "0.5")
        e5 = TargetPathConflict("msg", "/tmp/x", "file")
        e6 = TargetParentNotAuthorized("msg", "/tmp/x/y", "/tmp/x")

        for e in [e1, e2, e3, e4, e5, e6]:
            assert isinstance(e, Exception)

        assert e1.reason_code == "CODE_A"
        assert e1.field == "field1"
        assert e2.reason_code == "CODE_B"
        assert e2.audit_record == {"key": "val"}
        assert e4.version == "0.5"
        assert e5.target_path == "/tmp/x"
        assert e6.parent_path == "/tmp/x"


# ================================================================
# 14. 枚举值测试
# ================================================================

class TestEnums:
    def test_valid_modes(self):
        assert ProjectMode.CREATE_NEW_PROJECT.value == "create_new_project"
        assert ProjectMode.MODIFY_EXISTING_PROJECT.value == "modify_existing_project"
        assert VALID_MODES == {"create_new_project", "modify_existing_project"}

    def test_valid_policies(self):
        assert CompatibilityPolicy.STRICT.value == "strict"
        assert CompatibilityPolicy.COMPAT_READONLY.value == "compat_readonly"
        assert CompatibilityPolicy.NONE.value == "none"
        assert VALID_POLICIES == {"strict", "compat_readonly", "none"}

    def test_invalid_policy_rejected(self, tmpdir):
        d = {
            "context_id": "ctx-001",
            "workspace_roots": [str(tmpdir)],
            "authorized_roots": [str(tmpdir)],
            "allowed_paths": {"read": [str(tmpdir)], "write": [str(tmpdir)], "execute": [str(tmpdir)]},
            "target_project_path": str(tmpdir),
            "project_mode": "modify_existing_project",
            "created_at": "2026-01-01T00:00:00Z",
            "compatibility_policy": "invalid_policy",
        }
        with pytest.raises(TaskContextValidationError) as exc:
            validate_task_context(d)
        assert "invalid_policy" in str(exc.value)


# ================================================================
# 15. 现有协议无回归测试
# ================================================================

class TestNoRegression:
    """验证新增契约不影响现有 task_state_contract 的导入和使用。"""

    def test_task_state_contract_still_works(self):
        from task_state_contract import (
            TASK_STATE_PENDING, TASK_STATE_RUNNING, TASK_STATE_COMPLETED,
            TASK_STATE_FAILED, TASK_STATE_WAITING_AUTHORIZATION,
            TASK_STATES_ALL, transition_is_legal,
        )
        assert len(TASK_STATES_ALL) == 5
        assert transition_is_legal(TASK_STATE_PENDING, TASK_STATE_RUNNING)
        assert not transition_is_legal(TASK_STATE_COMPLETED, TASK_STATE_RUNNING)

    def test_task_context_does_not_break_existing_imports(self):
        from task_context_contract import TaskContext, ProjectMode
        assert TaskContext is not None
        assert ProjectMode is not None
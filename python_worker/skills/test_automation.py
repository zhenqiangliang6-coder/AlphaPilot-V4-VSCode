from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="test.automation",
            name="Test Automation",
            version="1.0.0",
            description="Guidance for pytest/unittest test generation, test coverage, and test-driven development.",
            triggers=(
                "test",
                "pytest",
                "unit test",
                "integration test",
                "e2e test",
                "end-to-end test",
                "test case",
                "测试",
                "单元测试",
                "集成测试",
                "端到端测试",
                "测试用例",
                "测试覆盖",
                "test coverage",
            ),
            priority=150,
            capabilities=("workspace.read", "tests.propose", "coverage.report"),
            guidance=(
                "For test work, follow the project's test framework (pytest/unittest). "
                "Use fixtures for dependency management, ensure test independence and repeatability. "
                "Cover normal cases, edge cases (empty inputs, single elements, boundaries), and error cases. "
                "Use clear assertions and pytest.raises for exception testing. "
                "Mock external dependencies (API calls, database) to keep tests fast and isolated. "
                "Target meaningful coverage of critical paths; avoid testing trivial getters/setters. "
                "This skill only proposes tests: test execution and coverage reporting require host authorization."
            ),
        )
    )

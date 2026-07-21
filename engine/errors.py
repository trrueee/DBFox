# -*- coding: utf-8 -*-
"""
DBFox 异常处理模块 (Errors Module)
--------------------------------------
这个模块定义了 DBFox 后端所有的自定义异常类。
在 Python 中，自定义异常是通过继承基类 `Exception` 来实现的。
"""

class DBFoxError(Exception):
    """
    DBFox 异常基类 (Base Error)
    
    所有 DBFox 自定义的业务异常都会继承这个类，这样在外部捕获异常时，
    可以通过 `except DBFoxError:` 一并捕获所有相关的错误。
    
    Python 知识点:
      - `class DBFoxError(Exception):` 表示创建一个名叫 DBFoxError 的类，它继承自 Python 的内置异常类 `Exception`。
      - `__init__` 是类的构造函数（初始化方法），在创建类的实例对象时会自动执行。
      - `self` 代表类实例化后的对象自身，用于绑定属性。
      - `message: str` 和 `code: str` 是类型注解（Type Hints），说明 message 应该是字符串类型，code 也应该是字符串类型。
      - `-> None` 说明这个方法没有返回值。
      - `super().__init__(message)` 用来调用父类 (即 Exception) 的构造函数，初始化异常的标准错误信息。
    """

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)  # 调用父类 Exception 的构造函数，把错误消息传递过去
        self.message = message     # 将详细错误消息绑定到实例属性 self.message
        self.code = code           # 将业务错误码（如 CONNECTION_FAILED）绑定到实例属性 self.code


class DataSourceConnectionError(DBFoxError):
    """
    数据源连接异常
    
    当连接目标数据库失败时抛出此异常。
    
    Python 知识点:
      - 继承自 `DBFoxError`，因此它本身也是一个 DBFoxError。
      - 覆写了父类的构造函数 `__init__`，但默认传入了具体的错误码 "CONNECTION_FAILED"。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONNECTION_FAILED")


class GuardrailValidationError(DBFoxError):
    """
    SQL 安全卫士 (Guardrail) 校验失败异常
    
    当用户执行的 SQL 查询未通过安全策略（例如存在 SQL 注入风险、执行了禁止的操作等）时抛出。
    
    Python 知识点:
      - `checks: list[dict[str, str]] | None = None` 是类型注解，表示 checks 可以是一个由字典组成的列表，字典的键值均为字符串；或者也可以是 None。默认值为 None。
      - `self.checks = checks or []` 是 Python 常用的简写，如果 checks 为 None 或空，就使用后面的默认空列表 `[]`。
    """

    def __init__(self, message: str, checks: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="GUARDRAIL_BLOCKED")
        self.checks = checks or []  # 记录详细的检查条目，比如具体哪一项安全规则没通过


class SQLExecutionError(DBFoxError):
    """
    SQL 执行异常
    
    当 SQL 语句在目标数据库中执行出错（如语法错误、表不存在等）时抛出。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_EXECUTION_FAILED")


class SQLQueryTimeoutError(DBFoxError):
    """
    SQL 查询超时异常
    
    当 SQL 查询执行时间超过了设定的最大时长限制时抛出。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_TIMEOUT")


class SQLQueryCancelledError(DBFoxError):
    """
    SQL 查询取消异常
    
    当用户在前端点击“取消执行”或后台主动撤销正在运行的查询时抛出。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_QUERY_CANCELLED")


class AIServiceError(DBFoxError):
    """
    AI 服务异常

    当 Text-to-SQL 智能大模型服务调用出错、返回格式非法或超时时抛出。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="AI_TRANSLATION_FAILED")


class ToolInputError(DBFoxError):
    """
    工具输入参数校验异常

    当 Agent 调用工具时传入了无效参数（缺少必填字段、值非法等）时抛出。
    由 @tool_handler 装饰器统一转换为 ToolObservation(status="failed")。
    不应包含敏感信息，错误消息会直接展示给前端。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="TOOL_INPUT_ERROR")


class NotFoundError(DBFoxError):
    """
    资源不存在异常
    """

    def __init__(self, message: str, code: str = "NOT_FOUND") -> None:
        super().__init__(message, code=code)


class BackupSourceMismatchError(DBFoxError):
    """A backup may only be restored to the connection profile that created it."""

    def __init__(self) -> None:
        super().__init__(
            "Backup source no longer matches this datasource.",
            code="BACKUP_SOURCE_MISMATCH",
        )


class ValidationException(DBFoxError):
    """
    请求参数/数据校验异常
    """

    def __init__(self, message: str, checks: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="VALIDATION_FAILED")
        self.checks = checks or []


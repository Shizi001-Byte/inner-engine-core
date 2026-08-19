#!/usr/bin/env python3
"""
观尘子引擎 V7.1 - CLI 命令行入口
支持启动、状态查询、任务提交、健康检查等操作
"""
import argparse
import json
import sys
import os

# 确保引擎目录在路径中
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from engine import EngineV71


def cmd_start(args):
    """启动引擎"""
    print(f"启动观尘子引擎 V{EngineV71.VERSION}...")
    engine = EngineV71(config_path=args.config)
    if not engine.initialize():
        print("初始化失败！")
        sys.exit(1)
    engine.start()
    print("引擎已启动。输入 'status' 查看状态，'quit' 退出。")

    try:
        while True:
            cmd = input("> ").strip().lower()
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "status":
                status = engine.get_status()
                print(json.dumps(status, ensure_ascii=False, indent=2))
            elif cmd == "health":
                report = engine.run_health_check()
                print(f"健康评分: {report['overall_score']} ({report['overall_status']})")
                for check in report["checks"]:
                    print(f"  {check['name']}: {check['score']} - {check['status']}")
            elif cmd == "tasks":
                stats = engine.task_scheduler.get_queue_stats()
                print(json.dumps(stats, ensure_ascii=False, indent=2))
            elif cmd == "modules":
                print("已加载模块:")
                for name, info in engine.get_status().get("modules", {}).items():
                    print(f"  {name}: v{info.get('version', '?')} - {info.get('status', '?')}")
            elif cmd == "help":
                print("可用命令: status, health, tasks, modules, quit")
            else:
                print(f"未知命令: {cmd}。输入 'help' 查看帮助。")
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        print("引擎已停止。")


def cmd_status(args):
    """查询引擎状态（单次）"""
    engine = EngineV71(config_path=args.config)
    engine.initialize()
    status = engine.get_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))


def cmd_health(args):
    """运行健康检查"""
    engine = EngineV71(config_path=args.config)
    engine.initialize()
    report = engine.run_health_check()
    print(f"=== 观尘子引擎健康检查报告 ===")
    print(f"时间: {report['timestamp']}")
    print(f"综合评分: {report['overall_score']} / 100")
    print(f"整体状态: {report['overall_status']}")
    print(f"\n--- 各维度评分 ---")
    for check in report["checks"]:
        status_icon = "✓" if check["status"] == "healthy" else "⚠" if check["status"] == "warning" else "✗"
        print(f"  {status_icon} {check['name']}: {check['score']}分 ({check['status']})")
        if "details" in check:
            for k, v in check["details"].items():
                print(f"      {k}: {v}")
    if report["alerts"]:
        print(f"\n--- 告警项 ({len(report['alerts'])}) ---")
        for alert in report["alerts"]:
            print(f"  ! {alert['name']}: {alert['status']}")


def cmd_test(args):
    """运行引擎自检"""
    print("运行引擎自检...")
    engine = EngineV71(config_path=args.config)

    # 测试初始化
    print("[1/5] 初始化...", end=" ")
    if engine.initialize():
        print("✓ 通过")
    else:
        print("✗ 失败")
        sys.exit(1)

    # 测试任务提交
    print("[2/5] 任务提交...", end=" ")
    task = engine.submit_task("custom", name="自检任务", description="CLI自检")
    if task:
        print(f"✓ 通过 (task_id={task.id})")
    else:
        print("✗ 失败")

    # 测试健康检查
    print("[3/5] 健康检查...", end=" ")
    report = engine.run_health_check()
    print(f"✓ 通过 (评分={report['overall_score']})")

    # 测试状态查询
    print("[4/5] 状态查询...", end=" ")
    status = engine.get_status()
    print(f"✓ 通过 (模块数={len(status['modules'])})")

    # 测试AI推理模块
    print("[5/5] AI推理模块...", end=" ")
    if engine.ai_inference:
        ai_status = engine.ai_inference.get_status()
        models_ok = sum(1 for m in ai_status["models"].values() if m.get("enabled") and m.get("api_configured"))
        print(f"✓ 通过 (就绪模型={models_ok}/{len(ai_status['models'])})")
    else:
        print("⚠ 未启用")

    print("\n=== 自检完成 ===")
    print(f"引擎版本: {engine.VERSION}")
    print(f"已加载插件: {', '.join(status['loaded_plugins']) or '无'}")
    print(f"健康评分: {report['overall_score']}")
    if engine.ai_inference:
        ai_status = engine.ai_inference.get_status()
        print(f"AI模型: {ai_status['total_models']}个配置, {ai_status['ready_models']}个就绪")
        print(f"今日Token: {ai_status['token_usage']['today_used']:,} / {ai_status['token_usage']['daily_limit']:,}")


def cmd_models(args):
    """查看AI模型状态"""
    engine = EngineV71(config_path=args.config)
    engine.initialize()
    if not engine.ai_inference:
        print("AI推理模块未启用")
        return
    status = engine.ai_inference.get_status()
    print("=== AI 推理模块状态 ===")
    print(f"总模型数: {status['total_models']}")
    print(f"就绪模型: {status['ready_models']}")
    print(f"今日Token使用: {status['token_usage']['today_used']:,} / {status['token_usage']['daily_limit']:,}")
    print(f"Token剩余: {status['token_usage']['remaining']:,} ({status['token_usage']['usage_percent']:.1f}%)")
    print(f"\n--- 模型详情 ---")
    for model_id, info in status["models"].items():
        is_ready = info.get("enabled") and info.get("api_configured")
        status_icon = "✓" if is_ready else "⚠" if info.get("enabled") else "✗"
        display = info.get("display_name", model_id)
        print(f"  {status_icon} {display} ({model_id})")
        print(f"      启用={info.get('enabled')}, API已配置={info.get('api_configured')}, 调用次数={info.get('call_count',0)}, Token={info.get('total_tokens',0):,}")


def cmd_chat(args):
    """与AI模型对话测试"""
    engine = EngineV71(config_path=args.config)
    engine.initialize()
    if not engine.ai_inference:
        print("AI推理模块未启用")
        return
    model = args.model or "guanchenzi_primary"
    task_type = args.task_type or "general"
    print(f"=== AI 对话测试 (模型={model}, 任务类型={task_type}) ===")
    print("输入消息，输入 'quit' 退出")
    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue
        result = engine.ai_inference.chat(
            prompt=user_input,
            model_id=model,
            task_type=task_type,
        )
        if result["success"]:
            print(f"\nAI> {result['content']}")
            print(f"  [Token: {result['usage']['total_tokens']}, 耗时: {result['latency_ms']}ms]")
        else:
            print(f"\n✗ 错误: {result['error']}")


def cmd_token(args):
    """查看Token使用统计"""
    engine = EngineV71(config_path=args.config)
    engine.initialize()
    if not engine.ai_inference:
        print("AI推理模块未启用")
        return
    usage = engine.ai_inference.get_token_usage()
    print("=== Token 使用统计 ===")
    print(f"今日已用: {usage['today_used']:,}")
    print(f"每日上限: {usage['daily_limit']:,}")
    print(f"剩余额度: {usage['remaining']:,}")
    print(f"使用比例: {usage['usage_percent']:.1f}%")
    print(f"是否超限: {'是' if usage['is_over_limit'] else '否'}")
    print(f"\n--- 各模型Token消耗 ---")
    for model_id, tokens in usage.get("by_model", {}).items():
        print(f"  {model_id}: {tokens:,}")


def main():
    parser = argparse.ArgumentParser(
        description="观尘子引擎 V7.1 - 命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py start              # 交互式启动引擎
  python cli.py health             # 运行健康检查
  python cli.py status             # 查看状态
  python cli.py test               # 运行自检
  python cli.py models             # 查看AI模型状态
  python cli.py token              # 查看Token使用统计
  python cli.py chat               # 与AI模型对话测试
  python cli.py chat -m xingjuan_creation  # 指定星卷创作模型
  python cli.py -c config.yaml start  # 指定配置文件
        """,
    )
    parser.add_argument("-c", "--config", help="配置文件路径", default=None)
    parser.add_argument("-v", "--version", action="version", version=f"观尘子引擎 V{EngineV71.VERSION}")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("start", help="交互式启动引擎")
    subparsers.add_parser("status", help="查询引擎状态")
    subparsers.add_parser("health", help="运行健康检查")
    subparsers.add_parser("test", help="运行引擎自检")
    subparsers.add_parser("models", help="查看AI模型状态")
    subparsers.add_parser("token", help="查看Token使用统计")

    chat_parser = subparsers.add_parser("chat", help="与AI模型对话测试")
    chat_parser.add_argument("-m", "--model", help="模型ID (默认: guanchenzi_primary)", default=None)
    chat_parser.add_argument("-t", "--task-type", help="任务类型 (默认: general)", default=None)

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "health":
        cmd_health(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "models":
        cmd_models(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "token":
        cmd_token(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

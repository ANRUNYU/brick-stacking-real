#!/usr/bin/env python3
"""P7 left J6/J7 controlled CAN diagnostic; does not certify mechanical motion."""
import math
import sys
import threading
import time

import can
from linkerbot.arm.p7.motor_v2 import MotorV2
from linkerbot.comm import CANMessageDispatcher

CAN_IFACE = "can2"
KP = 12.0
MOVE_DEG = 5.0
DURATION_S = 6.0
RATE_HZ = 100
MAX_FEEDBACK_AGE_S = 0.3
JOINT_LIMIT_RAD = 1.59  # from P7 left URDF; not a replacement for actual hardware limits


class CANMonitor:
    """Observe frames through a separate SocketCAN socket (not just queued sends)."""

    def __init__(self, iface, motor_id):
        self.bus = can.Bus(channel=iface, interface="socketcan", receive_own_messages=True)
        self.motor_id = motor_id
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.n_target = 0
        self.n_feedback = 0
        self.n_state = 0
        self.first_target = self.last_target = None
        self.first_feedback = self.last_feedback = None
        self.last_rest_ack_at = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                msg = self.bus.recv(timeout=0.04)
            except Exception:
                return
            if msg is None or msg.arbitration_id != self.motor_id or len(msg.data) != 8:
                continue
            data = bytes(msg.data)
            with self.lock:
                if data[:7] == b"\xff" * 7:
                    self.n_state += 1
                elif 0 <= data[0] <= 5:
                    self.n_feedback += 1
                    self.first_feedback = self.first_feedback or data.hex(" ")
                    self.last_feedback = data.hex(" ")
                    if data[0] == 0:
                        self.last_rest_ack_at = time.monotonic()
                else:
                    self.n_target += 1
                    self.first_target = self.first_target or data.hex(" ")
                    self.last_target = data.hex(" ")

    def report(self):
        with self.lock:
            print("\n===== SocketCAN实际帧统计 =====", flush=True)
            print(f"P-T-M目标帧: {self.n_target}; 驱动反馈帧: {self.n_feedback}; 状态命令帧: {self.n_state}", flush=True)
            print(f"首条目标帧: {self.first_target}", flush=True)
            print(f"末条目标帧: {self.last_target}", flush=True)
            print(f"首条反馈帧: {self.first_feedback}", flush=True)
            print(f"末条反馈帧: {self.last_feedback}", flush=True)

    def rest_ack_after(self, at):
        with self.lock:
            return self.last_rest_ack_at is not None and self.last_rest_ack_at > at

    def close(self):
        self.stop_event.set()
        self._thread.join(timeout=0.5)
        self.bus.shutdown()


def ask(word, message):
    while True:
        reply = input(message).strip().upper()
        if reply == word:
            return
        if reply in ("CANCEL", "QUIT", "EXIT"):
            raise RuntimeError("用户取消")
        print(f"输入不匹配；请输入 {word}，或输入 CANCEL 取消。", flush=True)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("6", "7"):
        sys.exit("用法：~/p7_sdk_venv/bin/python -u ~/p7_j67_verified.py 6  （或7）")
    joint = int(sys.argv[1])
    motor_id = 60 + joint
    print(f"LEFT P7 J{joint} / CAN {CAN_IFACE} / ID {motor_id}", flush=True)
    print(f"目标 +{MOVE_DEG}°，{DURATION_S}s，{RATE_HZ} Hz，Kp={KP}，默认Kd不修改", flush=True)
    print("只测试电机反馈，不自动认定机械腕关节已经旋转。", flush=True)
    print("开始前及退出时确保腕部可靠支撑；必须有可用急停；禁止其他程序同时控制can2。", flush=True)
    print("异常运动请使用现场急停；脚本检查不是硬件安全保护。", flush=True)

    ask("READY", "确认支撑、无干涉、急停可用，输入 READY: ")

    monitor = CANMonitor(CAN_IFACE, motor_id)
    try:
        with CANMessageDispatcher(CAN_IFACE) as bus:
            motor = MotorV2(motor_id, bus)
            enabled_requested = False
            heartbeat_started = False
            try:
                if not motor.check_alive(timeout_s=1.0):
                    raise RuntimeError("电机无响应")
                data = motor._read_flash_param(0x0B, timeout_s=1.0)
                mode = int.from_bytes(data[:4], "little", signed=True)
                if mode != 2:
                    raise RuntimeError(f"P-T-M模式不正确：{mode}，已中止（不会改Flash）")
                motor.read_initial_state(timeout_s=1.5)  # 发Rest获取初始反馈
                if motor.fault_code:
                    raise RuntimeError(f"初始故障码：{motor.fault_code}")
                motor.set_position_kp(KP)
                print(f"初始反馈角度={math.degrees(motor.angle.angle):+.3f}°", flush=True)
                ask("ENABLE", "准备单关节使能，输入 ENABLE: ")
                enabled_requested = True
                motor.enable()
                motor.start_polling()  # 必须保持心跳
                heartbeat_started = True
                motor.set_angle(motor.angle.angle)  # 当前位置保持，不跳目标
                time.sleep(0.4)
                age = time.time() - motor.angle.timestamp
                if not motor.enabled or motor.fault_code != 0 or age > MAX_FEEDBACK_AGE_S:
                    raise RuntimeError(f"使能反馈异常 enabled={motor.enabled}, fault={motor.fault_code}, age={age:.3f}s")
                start = motor.angle.angle
                goal = start + math.radians(MOVE_DEG)
                if not (-JOINT_LIMIT_RAD < goal < JOINT_LIMIT_RAD):
                    raise RuntimeError("目标超出URDF关节范围，停止")
                print(f"使能后反馈={math.degrees(start):+.3f}°，目标={math.degrees(goal):+.3f}°", flush=True)
                ask("MOVE", "确认允许做一次5°的电机目标测试，输入 MOVE: ")

                last_actual = start
                t0 = time.perf_counter()
                for k in range(int(DURATION_S * RATE_HZ) + 1):
                    deadline = t0 + k / RATE_HZ
                    delay = deadline - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    age = time.time() - motor.angle.timestamp
                    actual = motor.angle.angle
                    if age > MAX_FEEDBACK_AGE_S or not motor.enabled or motor.fault_code:
                        raise RuntimeError(f"失去安全反馈：age={age:.3f}s enabled={motor.enabled} fault={motor.fault_code}")
                    if abs(actual - last_actual) > math.radians(2.0):
                        raise RuntimeError("反馈角度出现单周期>2°跳变，已中止")
                    last_actual = actual
                    s = k / (DURATION_S * RATE_HZ)
                    fraction = 3 * s * s - 2 * s * s * s
                    target = start + (goal - start) * fraction
                    motor.set_angle(target)
                    if k % 50 == 0:
                        print(f"{k/RATE_HZ:4.1f}s 目标={math.degrees(target):+7.3f}° "
                              f"反馈={math.degrees(actual):+7.3f}° "
                              f"误差={math.degrees(target-actual):+6.3f}° "
                              f"扭矩反馈={motor.torque.torque:+.3f}Nm "
                              f"age={age:.3f}s fault={motor.fault_code}", flush=True)
                time.sleep(0.7)
                end = motor.angle.angle
                print("\n===== 测试结束（仅电机CAN反馈） =====", flush=True)
                print(f"目标变化：{MOVE_DEG:+.3f}°", flush=True)
                print(f"电机反馈变化：{math.degrees(end-start):+.3f}°", flush=True)
                print(f"剩余反馈误差：{math.degrees(goal-end):+.3f}°", flush=True)
                print("机械关节是否真的转动：需要操作人员肉眼确认，程序不判定", flush=True)
                print("完成后不会自动回零或反向运动。", flush=True)
                ask("RELEASE", "确认腕部可靠支撑后输入 RELEASE（错拼会再次提示）: ")
            except (KeyboardInterrupt, EOFError):
                print("\n测试被中断。警告：接下来解除使能，腕部可能下垂！", flush=True)
            except Exception as exc:
                print(f"\n测试中止：{type(exc).__name__}: {exc}", flush=True)
            finally:
                if heartbeat_started:
                    motor.stop_polling()  # 先停心跳，防止Rest后仍发控制帧
                if enabled_requested:
                    t_rest = time.monotonic()
                    motor.disable()  # 异步队列发送Rest
                    deadline = time.monotonic() + 1.0
                    while time.monotonic() < deadline and not monitor.rest_ack_after(t_rest):
                        time.sleep(0.02)
                    if monitor.rest_ack_after(t_rest):
                        print("解除使能：已收到来自驱动器的Rest状态反馈", flush=True)
                    else:
                        print("警告：未确认收到Rest状态反馈，请保持机械支撑并检查设备状态！", flush=True)
                monitor.report()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()

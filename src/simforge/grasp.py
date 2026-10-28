"""Gate 2 grasp controller: mink IK waypoint execution of a validated plan.

execute_plan(model, data, plan, ids) runs the full cycle from the plan's
own fields - approach over the part, descend, close, lift and HOLD,
transfer over the target zone, place, release, retreat - and returns
the telemetry trace (sample_state dicts) for the scorer to judge.

The controller NEVER reports success. It moves; scoring.py measures.
Motion is plan-driven (Gate 4 causality): approach_height_m sets the
hover height, speed_scale sets the target-follow speed, target_zone
sets the placement. All stepping goes through step_checked, so a
simulator warning or reset aborts the attempt instead of passing it.
"""
from __future__ import annotations

import math

import mink
import mujoco
import numpy as np

from simforge.scoring import sample_state
from simforge.sim.cell import step_checked

BASE_SPEED_MPS = 0.35        # multiplied by the plan's speed_scale
GRIPPER_OPEN = 255.0         # measured by probe_model.py, Oct 28
GRIPPER_CLOSED = 0.0
ATTEMPT_LIMIT_S = 30.0       # ratified Gate 2 attempt budget


def _field(plan, name):
    return plan[name] if isinstance(plan, dict) else getattr(plan, name)


def _mat_to_wxyz(R) -> np.ndarray:
    t = float(np.trace(R))
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = np.array([0.25 * s, (R[2, 1] - R[1, 2]) / s,
                      (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s])
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = np.array([(R[2, 1] - R[1, 2]) / s, 0.25 * s,
                      (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s])
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = np.array([(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s,
                      0.25 * s, (R[1, 2] + R[2, 1]) / s])
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = np.array([(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s,
                      (R[1, 2] + R[2, 1]) / s, 0.25 * s])
    return q / np.linalg.norm(q)


def _quat_mul(a, b) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ])


def _slerp(a, b, u) -> np.ndarray:
    d = float(np.dot(a, b))
    if d < 0.0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + u * (b - a)
        return q / np.linalg.norm(q)
    th = math.acos(max(-1.0, min(1.0, d)))
    s = math.sin(th)
    q = (math.sin((1 - u) * th) / s) * a + (math.sin(u * th) / s) * b
    return q / np.linalg.norm(q)


def execute_plan(model, data, plan, ids, log=print) -> list[dict]:
    """Run one full pick-and-place cycle. Returns the telemetry trace.

    Assumes the scene is already set (part placed, arm at home keyframe)
    and `data` has been forwarded. Raises RuntimeError on simulator
    faults (via step_checked) or if the attempt exceeds 30 s.
    """
    dt = float(model.opt.timestep)
    speed = BASE_SPEED_MPS * float(_field(plan, "speed_scale"))
    approach = float(_field(plan, "approach_height_m"))
    t_start = float(data.time)

    part_pos = np.array(data.xpos[ids.part_body], dtype=float)
    part_quat = np.array(data.xquat[ids.part_body], dtype=float)
    yaw = math.atan2(2.0 * (part_quat[0] * part_quat[3] + part_quat[1] * part_quat[2]),
                     1.0 - 2.0 * (part_quat[2] ** 2 + part_quat[3] ** 2))

    zone_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM,
                                 str(_field(plan, "target_zone")))
    if zone_gid < 0:
        raise RuntimeError(f"target zone geom {_field(plan, 'target_zone')!r} not found")
    zone_center = np.array(model.geom_pos[zone_gid], dtype=float)

    # Grasp geometry measured, not assumed: at the home keyframe the
    # hand already points down, so the finger pads' world-z span below
    # the hand origin there is the span at grasp orientation too (yaw
    # about world z does not change it). Center that span on the part.
    hand0 = np.array(data.xpos[ids.hand_body], dtype=float)
    pad_zs = [float(data.geom_xpos[g][2]) for g in ids.pad_geoms]
    drop_center = hand0[2] - 0.5 * (min(pad_zs) + max(pad_zs))
    grasp_z = part_pos[2] + drop_center
    log(f"geometry: hand home z={hand0[2]:.3f}, pad span z "
        f"[{min(pad_zs):.3f}, {max(pad_zs):.3f}], drop_center={drop_center:.3f}, "
        f"grasp hand z={grasp_z:.3f}, part yaw={math.degrees(yaw):.1f} deg")

    home_wxyz = _mat_to_wxyz(np.array(data.xmat[ids.hand_body]).reshape(3, 3))
    yaw_q = np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])
    grasp_wxyz = _quat_mul(yaw_q, home_wxyz)

    configuration = mink.Configuration(model)
    if hasattr(configuration, "update_from_data"):
        configuration.update_from_data(data)
    else:
        configuration.update(data.qpos.copy())
    frame_task = mink.FrameTask(frame_name="hand", frame_type="body",
                                position_cost=1.0, orientation_cost=1.0,
                                lm_damping=1e-3)
    posture_task = mink.PostureTask(model, cost=1e-2)
    posture_task.set_target_from_configuration(configuration)
    tasks = [frame_task, posture_task]

    samples: list[dict] = []
    target_pos = hand0.copy()
    target_wxyz = home_wxyz.copy()
    gripper = [GRIPPER_OPEN]

    def step_once():
        se3 = mink.SE3.from_rotation_and_translation(
            mink.SO3(target_wxyz), target_pos)
        frame_task.set_target(se3)
        vel = mink.solve_ik(configuration, tasks, dt, solver="daqp",
                            damping=1e-2)
        configuration.integrate_inplace(vel, dt)
        data.ctrl[:7] = configuration.q[:7]
        data.ctrl[7] = gripper[0]
        step_checked(model, data, 1)
        samples.append(sample_state(model, data, ids))
        if float(data.time) - t_start > ATTEMPT_LIMIT_S:
            raise RuntimeError("attempt exceeded the 30 s limit")

    def dwell(duration_s, label):
        for _ in range(int(round(duration_s / dt))):
            step_once()
        s = samples[-1]
        log(f"  [{label}] t={s['t']:.2f} part={np.round(s['part'], 3)} "
            f"grip={s['grip_force_n']:.2f} N")

    def move_to(goal_pos, min_s, label):
        nonlocal target_pos, target_wxyz
        start_pos, start_q = target_pos.copy(), target_wxyz.copy()
        goal_pos = np.array(goal_pos, dtype=float)
        dist = float(np.linalg.norm(goal_pos - start_pos))
        steps = max(int(round(max(dist / speed, min_s) / dt)), 1)
        for k in range(steps):
            u = (k + 1) / steps
            uu = u * u * (3 - 2 * u)  # smoothstep: gentle ends
            target_pos = start_pos + (goal_pos - start_pos) * uu
            target_wxyz = _slerp(start_q, grasp_wxyz, uu)
            step_once()
        target_pos, target_wxyz = goal_pos, grasp_wxyz.copy()
        s = samples[-1]
        log(f"  [{label}] t={s['t']:.2f} hand={np.round(s['hand'], 3)} "
            f"part={np.round(s['part'], 3)} grip={s['grip_force_n']:.2f} N")

    def set_gripper(value, duration_s, label):
        start = gripper[0]
        steps = max(int(round(duration_s / dt)), 1)
        for k in range(steps):
            gripper[0] = start + (value - start) * (k + 1) / steps
            step_once()
        fids = [int(model.jnt_qposadr[j]) for j in range(model.njnt)
                if "finger" in (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or "")]
        fingers = [round(float(data.qpos[a]), 4) for a in fids]
        log(f"  [{label}] gripper ctrl={value:.0f}, finger qpos={fingers}")

    px, py = float(part_pos[0]), float(part_pos[1])
    zx, zy = float(zone_center[0]), float(zone_center[1])
    lift_z = grasp_z + approach + 0.05

    dwell(0.4, "settle, gripper open")
    move_to([px, py, grasp_z + approach], 0.8, "approach")
    move_to([px, py, grasp_z], 0.8, "descend")
    set_gripper(GRIPPER_CLOSED, 0.9, "close")
    move_to([px, py, lift_z], 4.2, "lift + hold")
    move_to([zx, zy, lift_z], 1.2, "transfer")
    move_to([zx, zy, grasp_z + 0.002], 1.0, "place")
    set_gripper(GRIPPER_OPEN, 0.9, "release")
    move_to([zx, zy, lift_z], 1.0, "retreat")
    dwell(1.6, "post-release rest")
    return samples

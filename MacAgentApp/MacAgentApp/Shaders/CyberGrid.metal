#include <metal_stdlib>
using namespace metal;

// Simple hash for noise
float cyberHash(float2 p) {
    float3 p3 = fract(float3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

/// 赛博朋克网格背景 — 完全 GPU 渲染
/// 效果：抗锯齿网格线 + 双向扫描波 + 脉冲节点 + 暗角 + 噪点纹理
[[ stitchable ]] half4 cyberGrid(
    float2 position,
    half4 currentColor,
    float2 viewSize,
    float time
) {
    // ═══════════════════════ 参数 ═══════════════════════
    float spacing     = 44.0;
    float wavePeriod  = 18.0;       // 主波周期（秒）
    float waveRadius  = 160.0;      // 波浪影响半径
    float wave2Period = 30.0;       // 副波周期
    float wave2Radius = 100.0;

    // ═══════════════════════ 颜色 ═══════════════════════
    half3 bgColor  = half3(0.04h, 0.04h, 0.08h);   // CyberColor.bg0
    half3 cyan     = half3(0.00h, 0.90h, 1.00h);    // CyberColor.cyan

    // ═══════════════════════ 扫描波 ═══════════════════════
    // 主波：从上往下扫
    float totalRange = viewSize.y + waveRadius * 2.0;
    float waveY      = fract(time / wavePeriod) * totalRange - waveRadius;
    float waveDist   = abs(position.y - waveY);
    float waveFactor = waveDist < waveRadius
        ? pow(1.0 - waveDist / waveRadius, 2.0)
        : 0.0;

    // 副波：从下往上扫（更慢、更窄、更暗）
    float total2     = viewSize.y + wave2Radius * 2.0;
    float wave2Y     = (1.0 - fract(time / wave2Period)) * total2 - wave2Radius;
    float wave2Dist  = abs(position.y - wave2Y);
    float wave2Factor = wave2Dist < wave2Radius
        ? pow(1.0 - wave2Dist / wave2Radius, 2.0) * 0.25
        : 0.0;

    float combinedWave = min(1.0, waveFactor + wave2Factor);

    // ═══════════════════════ 网格线 ═══════════════════════
    float2 gridPos = fmod(position, spacing);

    // 到最近网格线的距离（用于抗锯齿）
    float distX = min(gridPos.x, spacing - gridPos.x);
    float distY = min(gridPos.y, spacing - gridPos.y);

    // 抗锯齿线宽
    float dimLineW    = 0.6;
    float brightLineW = 1.0 + combinedWave * 0.4;

    float lineX = 1.0 - smoothstep(0.0, dimLineW, distX);
    float lineY = 1.0 - smoothstep(0.0, dimLineW, distY);
    float gridDim = max(lineX, lineY);

    float lineXB = 1.0 - smoothstep(0.0, brightLineW, distX);
    float lineYB = 1.0 - smoothstep(0.0, brightLineW, distY);
    float gridBright = max(lineXB, lineYB);

    // ═══════════════════════ 交叉节点 ═══════════════════════
    float2 nodeOff;
    nodeOff.x = distX;
    nodeOff.y = distY;
    float nodeDist = length(nodeOff);

    float nodeBaseR = 1.8;
    float nodeGlowR = nodeBaseR + combinedWave * 4.0;

    float nodeCore = 1.0 - smoothstep(0.0, nodeBaseR, nodeDist);
    float nodeGlow = 1.0 - smoothstep(nodeBaseR * 0.5, nodeGlowR, nodeDist);

    // 脉冲效果：节点随波浪闪烁
    float2 cellID = floor(position / spacing);
    float pulse = sin(time * 2.5 + cellID.x * 1.7 + cellID.y * 2.3) * 0.5 + 0.5;
    float nodePulse = combinedWave > 0.01 ? (0.7 + 0.3 * pulse) : 1.0;

    // ═══════════════════════ Alpha 合成 ═══════════════════════
    float dimAlpha    = 0.055;
    float brightAlpha = 0.30;

    // 暗网格线
    float gridAlpha = gridDim * dimAlpha;
    // 波浪区域亮网格线
    gridAlpha += gridBright * brightAlpha * combinedWave;

    // 节点
    float nodeAlpha = nodeCore * dimAlpha * 1.5;
    nodeAlpha += nodeGlow * 0.45 * combinedWave * nodePulse;

    float totalAlpha = max(gridAlpha, nodeAlpha);

    // 波浪区域环境辉光
    totalAlpha += combinedWave * 0.015;

    // ═══════════════════════ 扫描线纹理 ═══════════════════════
    float scanLine = pow(abs(sin(position.y * 1.5)), 80.0) * 0.025;

    // ═══════════════════════ 暗角效果 ═══════════════════════
    float2 uv = position / viewSize;
    float vignette = 1.0 - 0.35 * pow(length(uv - 0.5) * 1.5, 2.5);

    // ═══════════════════════ 噪点纹理 ═══════════════════════
    float noise = cyberHash(floor(position * 0.8) + fmod(time, 60.0) * 7.0) * 0.006;

    // ═══════════════════════ 波浪颜色混合 ═══════════════════════
    // 主波青色，副波带一点紫色
    half3 waveColor = cyan;
    if (wave2Factor > 0.01) {
        float purpleMix = wave2Factor / max(combinedWave, 0.001);
        waveColor = mix(cyan, half3(0.30h, 0.60h, 1.00h), half(purpleMix * 0.4));
    }

    // ═══════════════════════ 最终颜色 ═══════════════════════
    half3 finalColor = bgColor * half(vignette)
                     + waveColor * half(totalAlpha)
                     + half(scanLine) * cyan * 0.3h
                     + half(noise);

    return half4(finalColor, 1.0h);
}

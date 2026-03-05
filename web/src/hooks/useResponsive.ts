import { useState, useEffect } from 'react';

export interface ResponsiveState {
  /** 视口宽度 */
  width: number;
  /** 视口高度 */
  height: number;
  /** 手机端 (<768px) */
  isMobile: boolean;
  /** 平板端 (768px - 1024px) */
  isTablet: boolean;
  /** 桌面端 (>1024px) */
  isDesktop: boolean;
  /** 触控设备 */
  isTouch: boolean;
}

/**
 * 设置 CSS 变量 --vh，用于 iOS Safari 100vh 不等于可视区域的兼容。
 * 配合 .h-screen-safe { height: calc(var(--vh, 1vh) * 100); }
 */
function setVhVar() {
  const vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
}

function getState(): ResponsiveState {
  const w = window.innerWidth;
  const h = window.innerHeight;
  return {
    width: w,
    height: h,
    isMobile: w < 768,
    isTablet: w >= 768 && w <= 1024,
    isDesktop: w > 1024,
    isTouch: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
  };
}

export function useResponsive(): ResponsiveState {
  const [state, setState] = useState(getState);

  useEffect(() => {
    // 初始设置 --vh
    setVhVar();

    let raf: number;
    const handler = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        setVhVar();
        setState(getState());
      });
    };
    window.addEventListener('resize', handler);
    window.addEventListener('orientationchange', handler);
    return () => {
      window.removeEventListener('resize', handler);
      window.removeEventListener('orientationchange', handler);
      cancelAnimationFrame(raf);
    };
  }, []);

  return state;
}

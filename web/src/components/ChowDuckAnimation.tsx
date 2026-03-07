import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
  isActive: boolean;
  duckType: string;
  /** egg | local：完成时显示 🥚 或 🦆 */
  mode?: 'egg' | 'local';
  onComplete?: () => void;
}

const DUCK_ICONS: Record<string, string> = {
  crawler: '🕷️',
  coder: '💻',
  image: '🎨',
  video: '🎬',
  tester: '🧪',
  designer: '🎯',
  general: '🦆',
};

/**
 * 吃鸭子动画
 * 向——————🦆——————口
 * 鸭子从右移向左边的嘴，被吃掉后生成蛋
 */
const ChowDuckAnimation: React.FC<Props> = ({ isActive, duckType, mode = 'egg', onComplete }) => {
  const [phase, setPhase] = useState<'idle' | 'eating' | 'digesting' | 'egg' | 'done'>('idle');

  useEffect(() => {
    if (!isActive) {
      setPhase('idle');
      return;
    }

    setPhase('eating');

    // 强制至少 3s 吃鸭子动画（eating 2s + digesting 1s），给后端创建配置争取时间
    const t1 = setTimeout(() => setPhase('digesting'), 2000);
    const t2 = setTimeout(() => setPhase('egg'), 3000);
    const t3 = setTimeout(() => {
      setPhase('done');
      onComplete?.();
    }, 4200);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [isActive, onComplete]);

  const icon = DUCK_ICONS[duckType] || '🦆';

  if (!isActive && phase === 'idle') return null;

  return (
    <div
      className="relative w-full overflow-hidden rounded-xl py-6 px-4"
      style={{ background: 'var(--bg-recessed)', minHeight: 100 }}
    >
      {/* 轨道线 */}
      <div
        className="absolute left-8 right-8 top-1/2 h-px"
        style={{ background: 'var(--border)', transform: 'translateY(-50%)' }}
      />

      {/* 嘴巴（左侧） */}
      <motion.div
        className="absolute left-4 top-1/2 text-2xl select-none"
        style={{ transform: 'translateY(-50%)' }}
        animate={phase === 'eating' ? { scale: [1, 1.3, 1], rotate: [0, -10, 0] } : {}}
        transition={{ repeat: 3, duration: 0.5 }}
      >
        👄
      </motion.div>

      {/* 鸭子（从右向左移动） */}
      <AnimatePresence>
        {(phase === 'eating') && (
          <motion.div
            className="absolute top-1/2 text-3xl select-none"
            style={{ transform: 'translateY(-50%)' }}
            initial={{ right: 16 }}
            animate={{ right: 'calc(100% - 56px)' }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ duration: 2, ease: 'easeIn' }}
          >
            {icon}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 消化中 */}
      <AnimatePresence>
        {phase === 'digesting' && (
          <motion.div
            className="absolute left-1/2 top-1/2 text-xs font-medium"
            style={{ color: 'var(--text-secondary)', transform: 'translate(-50%, -50%)' }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
              className="inline-block text-xl"
            >
              ⚙️
            </motion.div>
            <div className="mt-1 text-center">正在生成...</div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 结果出现（蛋或本地 Duck） */}
      <AnimatePresence>
        {(phase === 'egg' || phase === 'done') && (
          <motion.div
            className="absolute right-8 top-1/2 select-none"
            style={{ transform: 'translateY(-50%)' }}
            initial={{ scale: 0, y: -20 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 15 }}
          >
            <span className="text-3xl">{mode === 'local' ? '🦆' : '🥚'}</span>
            <motion.div
              className="text-[10px] font-semibold mt-1 text-center"
              style={{ color: 'var(--accent)' }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              {mode === 'local' ? 'Duck Ready!' : 'Egg Ready!'}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 进度条 */}
      {phase !== 'idle' && phase !== 'done' && (
        <div className="absolute bottom-2 left-8 right-8 h-1 rounded-full overflow-hidden" style={{ background: 'var(--bg-surface)' }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: 'var(--gradient-accent)' }}
            initial={{ width: '0%' }}
            animate={{
              width: phase === 'eating' ? '50%' : phase === 'digesting' ? '80%' : '100%',
            }}
            transition={{ duration: phase === 'eating' ? 2 : 1 }}
          />
        </div>
      )}
    </div>
  );
};

export default ChowDuckAnimation;

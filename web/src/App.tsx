import React from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { useWSDispatcher } from './hooks/useWSDispatcher';

const App: React.FC = () => {
  useWSDispatcher();
  return (
    <ErrorBoundary>
      <Layout />
    </ErrorBoundary>
  );
};

export default App;

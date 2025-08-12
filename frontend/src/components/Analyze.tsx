import * as React from 'react';
console.log('[Analyze] React.version =', React.version, 'same?', (window as any).__reactA === React);

export const Analyze: React.FC = () => {
  return <div>Analyze</div>;
};

export default Analyze;
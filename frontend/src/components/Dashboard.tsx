import * as React from 'react';
console.log('[Dashboard] React.version =', React.version, 'same?', (window as any).__reactA === React);

const Dashboard: React.FC = () => {
  return <div>Dashboard</div>;
};

export default Dashboard;
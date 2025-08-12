// src/types/react-player.d.ts
declare module 'react-player' {
  import * as React from 'react';

  export interface ReactPlayerProps {
    url?: string | string[];
    playing?: boolean;
    controls?: boolean;
    loop?: boolean;
    muted?: boolean;
    width?: string | number;
    height?: string | number;
    [key: string]: any;
  }

  export default class ReactPlayer extends React.Component<ReactPlayerProps> {}
}

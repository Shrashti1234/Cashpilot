import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
 plugins:[react()],
 build:{
  chunkSizeWarningLimit:500,
  rollupOptions:{
   output:{
    manualChunks(id){
     if(id.includes('node_modules/recharts/') || id.includes('node_modules/d3-')) return 'charts';
     if(id.includes('node_modules/oidc-client-ts/') || id.includes('node_modules/oidc-client-ts')) return 'identity';
    }
   }
  }
 }
});

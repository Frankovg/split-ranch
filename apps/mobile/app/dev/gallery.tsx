import { Redirect } from 'expo-router';
import { GalleryScreen } from '@/features/dev/GalleryScreen';

/** Component gallery, development builds only (docs/13 §7). */
export default function GalleryRoute() {
  if (!__DEV__) return <Redirect href="/" />;
  return <GalleryScreen />;
}

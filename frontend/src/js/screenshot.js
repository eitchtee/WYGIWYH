// html2canvas can't parse daisyUI 5's oklch() colors; this renders through the browser instead
import {domToBlob} from 'modern-screenshot';

window.domToBlob = domToBlob;

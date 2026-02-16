import PullToRefresh from 'pulltorefreshjs';

const isOverlayOpen = () => !!document.querySelector('.offcanvas.show, .swal2-container');

const isIosPwa = () => {
    const ua = window.navigator.userAgent.toLowerCase();
    const isIos = /iphone|ipad|ipod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isStandalone = window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;
    return isIos && isStandalone;
};

const ptrMarkup = `
<div class="__PREFIX__box">
  <div class="__PREFIX__content">
    <div class="__PREFIX__icon"></div>
    <div class="__PREFIX__text"></div>
  </div>
</div>
`;

const ptrStyles = `
.__PREFIX__ptr {
  box-shadow: inset 0 -3px 5px rgba(0, 0, 0, 0.12);
  pointer-events: none;
  font-size: 0.85em;
  font-weight: bold;
  top: 0;
  height: 0;
  transition: height 0.3s, min-height 0.3s;
  text-align: center;
  width: 100%;
  overflow: hidden;
  display: flex;
  align-items: flex-end;
  align-content: stretch;
}

.__PREFIX__box {
  padding: 10px;
  flex-basis: 100%;
}

.__PREFIX__pull {
  transition: none;
}

.__PREFIX__text {
  margin-top: .33em;
  color: var(--color-base-content);
}

.__PREFIX__icon {
  color: var(--color-base-content);
  transition: transform .3s;
}

/*
When at the top of the page, disable vertical overscroll so passive touch
listeners can take over.
*/
.__PREFIX__top {
  touch-action: pan-x pan-down pinch-zoom;
}

.__PREFIX__release .__PREFIX__icon {
  transform: rotate(180deg);
}
`;

const getPtrStrings = () => {
    const ptrStringsEl = document.querySelector('#ptr-i18n');
    return {
        pull: ptrStringsEl?.dataset.pull,
        release: ptrStringsEl?.dataset.release,
        refreshing: ptrStringsEl?.dataset.refreshing
    };
};

const initPullToRefresh = () => {
    const ptrStrings = getPtrStrings();

    PullToRefresh.destroyAll();
    let ptr = PullToRefresh.init({
        mainElement: 'body',
        triggerElement: '#content',
        getMarkup() {
            return ptrMarkup;
        },
        getStyles() {
            return ptrStyles;
        },
        instructionsPullToRefresh: ptrStrings.pull || 'Pull down to refresh',
        instructionsReleaseToRefresh: ptrStrings.release || 'Release to refresh',
        instructionsRefreshing: ptrStrings.refreshing || 'Refreshing',
        shouldPullToRefresh() {
            return isIosPwa() && !isOverlayOpen() && window.scrollY === 0;
        },
        onRefresh() {
            window.location.reload();
        }
    });
};

if (isIosPwa()) {
    initPullToRefresh();

    document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.detail.target === document.body) {
            initPullToRefresh();
        }
});
}

import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import Config from './__federation_expose_Config-DYx8o3Pp.js';

const {createApp,defineCustomElement} = await importShared('vue');

customElements.define('usermonitor-config', defineCustomElement(Config));

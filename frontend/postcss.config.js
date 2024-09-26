const postcssPresetEnv = require("postcss-preset-env");
const tailwindcss = require('tailwindcss');

module.exports = {
    plugins: [postcssPresetEnv({
        /* use stage 2 features + disable logical properties and values rule */
        stage: 2,
        features: {
            'logical-properties-and-values': false
        }
    }), tailwindcss],
};

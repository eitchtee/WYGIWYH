const glob = require("glob");
const Path = require("path");
const { CleanWebpackPlugin } = require("clean-webpack-plugin");
const CopyWebpackPlugin = require("copy-webpack-plugin");
const WebpackAssetsManifest = require("webpack-assets-manifest").WebpackAssetsManifest;
// eslint-disable-next-line no-unused-vars
const webpack = require("webpack");

const getEntryObject = () => {
    const entries = {};
    glob.sync(Path.join(__dirname, "../src/application/*.js")).forEach((path) => {
        const name = Path.basename(path, ".js");
        entries[name] = path;
    });
    return entries;
};

module.exports = {
    entry: getEntryObject(),
    output: {
        path: Path.join(__dirname, "../build"),
        filename: "js/[name].js",
        publicPath: "/static/",
        assetModuleFilename: "[path][name][ext]",
    },
    // optimization: {
    //     splitChunks: {
    //         chunks: "all",
    //     },
    //
    //     runtimeChunk: "single",
    // },
    plugins: [
        new CleanWebpackPlugin(),
        new CopyWebpackPlugin({
            patterns: [
                {from: Path.resolve(__dirname, "../vendors"), to: "vendors"},
            ],
        }),
        new CopyWebpackPlugin({
            patterns: [
                {from: Path.resolve(__dirname, "../assets"), to: "assets"},
            ],
        }),
        new WebpackAssetsManifest({
            entrypoints: true,
            output: "manifest.json",
            writeToDisk: true,
            publicPath: true,
        }),
    ],
    resolve: {
        alias: {
            "~": Path.resolve(__dirname, "../src"),
            jquery: "jquery/dist/jquery"
        },
    },
    module: {
        rules: [
            {
                test: /\.mjs$/,
                include: /node_modules/,
                type: "javascript/auto",
            },
            {
                test: /\.(ico|jpg|jpeg|png|gif|eot|otf|webp|svg|ttf|woff|woff2)(\?.*)?$/,
                type: "asset",
            },
            {
                test: /\.css$/i,
                include: Path.resolve(__dirname, 'src'),
                use: ['style-loader', 'css-loader', 'postcss-loader'],
            },
        ],
    },
};

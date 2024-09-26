import TomSelect from "tom-select";
import * as Popper from "@popperjs/core";


const multiple_config = {
    plugins: {
        'checkbox_options': {
            'checkedClassNames': ['ts-checked'],
            'uncheckedClassNames': ['ts-unchecked'],
        },
        'clear_button': {
            'title': 'Limpar',
        },
        "remove_button": {
            "title": 'Remover',
        }
    },
    render: {
        no_results: function () {
            return '<div class="no-results">Nenhum resultado encontrado...</div>';
        },
    },
    onInitialize: function () {
        //this.popper = Popper.createPopper(this.control,this.dropdown);


        this.popper = Popper.createPopper(this.control, this.dropdown, {
            placement: "bottom-start",
            modifiers: [
                {
                    name: "sameWidth",
                    enabled: true,
                    fn: ({state}) => {
                        state.styles.popper.width = `${state.rects.reference.width}px`;
                    },
                    phase: "beforeWrite",
                    requires: ["computeStyles"],
                }
            ]

        });
    },
    onDropdownOpen: function () {
        this.popper.update();
    }
};


const single_config = {
    allowEmptyOption: false,
    // render: {
    //     no_results: function () {
    //         return '<div class="no-results">-------</div>';
    //     },
    // },
    onInitialize: function () {
        this.popper = Popper.createPopper(this.control, this.dropdown, {
            placement: "bottom-start",
            modifiers: [
                {
                    name: "sameWidth",
                    enabled: true,
                    fn: ({state}) => {
                        state.styles.popper.width = `${state.rects.reference.width}px`;
                    },
                    phase: "beforeWrite",
                    requires: ["computeStyles"],
                }
            ]

        });

    },
    onDropdownOpen: function () {
        this.popper.update();
    }
};

document.querySelectorAll('.selectmultiple').forEach((el)=>{
    new TomSelect(el, multiple_config);
});

document.querySelectorAll('.select').forEach((el)=>{
    new TomSelect(el, single_config);
});

document.querySelectorAll('.csvselect').forEach((el)=>{
    new TomSelect(el, single_config);
});
